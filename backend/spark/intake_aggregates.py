"""Spark batch job — intake statistics recomputed from the raw lake.

Why this exists as a batch job at all, given Postgres already answers most of
these questions: the lake is the *immutable* record and the database is a
derived, mutable view of it. Recomputing from raw is what makes the derived
view auditable — the job has already caught divergence between the two, which
is the whole point of keeping the raw log.

It also covers the analysis the serving database is the wrong tool for:
scanning every document ever collected, unindexed, on columns nobody planned
for. That is a full scan in Postgres and a partitioned read here.

**The small-file problem is real here and is handled explicitly.** The lake
writes one pretty-printed JSON document per event, which is right for an
immutable audit record and wrong for analytics: `multiLine` JSON cannot be
split, so Spark schedules one task per file and 44k files means 44k tasks.
The first measured version of this job re-read all of them once per action and
was still running after 11 minutes. So the job materialises a columnar
**silver** layer once (`--refresh`), then every aggregate reads that instead.
Bronze stays the immutable record; silver is disposable and rebuildable from
it.

Reads either backend (the layout is identical):
    python spark/intake_aggregates.py --source local
    python spark/intake_aggregates.py --source s3

Writes Parquet back to the lake under `_aggregates/`, and prints a reconcile
against the live database when it can reach one.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

def _raw_schema():
    from pyspark.sql import types as T

    return T.StructType(
        [
            T.StructField("id", T.StringType()),
            T.StructField("source_type", T.StringType()),
            T.StructField("collected_at", T.StringType()),
            T.StructField("schema_version", T.IntegerType()),
            T.StructField(
                "payload",
                T.StructType(
                    [
                        T.StructField("city_hint", T.StringType()),
                        T.StructField("is_noise", T.BooleanType()),
                        T.StructField("media", T.StringType()),
                    ]
                ),
            ),
        ]
    )


LAKE_LOCAL = "data/raw"
OUT_LOCAL = "data/aggregates"
SILVER_LOCAL = "data/silver/intake"


def build_session(source: str):
    from pyspark.sql import SparkSession

    builder = (
        SparkSession.builder.appName("nwap-intake-aggregates")
        .master("local[*]")
        # The lake is many small JSON files; without this Spark makes one
        # partition per file and spends all its time in task overhead.
        # The lake is ~44k files of a few hundred bytes each. A coarse
        # maxPartitionBytes collapses the whole scan into one task (measured:
        # a single task still running after 11 minutes); a fine one spreads
        # the unsplittable files across cores.
        .config("spark.sql.files.maxPartitionBytes", "1m")
        .config("spark.sql.files.openCostInBytes", "128k")
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.ui.enabled", "false")
    )
    if source == "s3":
        builder = (
            builder.config(
                "spark.jars.packages",
                "org.apache.hadoop:hadoop-aws:3.4.1,software.amazon.awssdk:bundle:2.24.6",
            )
            .config("spark.hadoop.fs.s3a.endpoint", os.environ["S3_ENDPOINT_URL"])
            .config("spark.hadoop.fs.s3a.access.key", os.environ["S3_ACCESS_KEY"])
            .config("spark.hadoop.fs.s3a.secret.key", os.environ["S3_SECRET_KEY"])
            # MinIO serves one host, not bucket-per-subdomain.
            .config("spark.hadoop.fs.s3a.path.style.access", "true")
            .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
            .config(
                "spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider",
            )
        )
    return builder.getOrCreate()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["local", "s3"], default="local")
    ap.add_argument("--bucket", default=os.environ.get("S3_BUCKET", "nwap-raw"))
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="rebuild the silver layer from raw JSON (slow: one task per file)",
    )
    args = ap.parse_args()

    from pyspark.sql import functions as F

    global RAW_SCHEMA
    RAW_SCHEMA = _raw_schema()

    if args.source == "s3":
        in_path = f"s3a://{args.bucket}/*/*/*/*/*.json"
        out_path = f"s3a://{args.bucket}/_aggregates"
        silver_path = f"s3a://{args.bucket}/_silver/intake"
    else:
        in_path = f"{LAKE_LOCAL}/*/*/*/*/*.json"
        out_path = OUT_LOCAL
        silver_path = SILVER_LOCAL

    spark = build_session(args.source)
    spark.sparkContext.setLogLevel("ERROR")

    def silver_exists() -> bool:
        if args.source == "s3":
            return False  # cheaper to just rebuild than to probe the object store
        from pathlib import Path

        return Path(silver_path).exists()

    if args.refresh or not silver_exists():
        t0 = time.time()
        # multiLine because each document is written pretty-printed, one object
        # per file — not JSON Lines. This is the expensive read.
        #
        # The schema is declared rather than inferred for two reasons: schema
        # inference is a full extra pass over every file (measured at ~90s for
        # 44k files), and an inferred schema silently changes shape when a new
        # payload key appears, which would break the aggregates downstream
        # rather than fail loudly here.
        raw = (
            spark.read.schema(RAW_SCHEMA)
            .option("multiLine", "true")
            .json(in_path)
        )
        parts = raw.rdd.getNumPartitions()
        print(f"scan parallelism: {parts} partitions")

        # IST is what an Indian operations centre reads the clock in; UTC
        # buckets would put the monsoon evening peak in the wrong day.
        ist = F.from_utc_timestamp(F.to_timestamp("collected_at"), "Asia/Kolkata")
        projected = raw.select(
            F.col("id"),
            F.col("source_type"),
            ist.alias("ist"),
            F.to_date(ist).alias("day_ist"),
            F.hour(ist).alias("hour_ist"),
            F.col("payload.city_hint").alias("city"),
            F.coalesce(F.col("payload.is_noise"), F.lit(False)).alias("is_noise"),
            F.col("payload.media").isNotNull().alias("has_media"),
        )
        # Partitioned by source_type so a per-source question reads one
        # directory instead of the whole history.
        projected.write.mode("overwrite").partitionBy("source_type").parquet(silver_path)
        print(f"\nbuilt silver layer from raw JSON in {time.time() - t0:.1f}s → {silver_path}")
    else:
        print(f"\nusing existing silver layer at {silver_path} (--refresh to rebuild)")

    t0 = time.time()
    enriched = spark.read.parquet(silver_path)
    total = enriched.count()
    print(f"read {total:,} rows from silver in {time.time() - t0:.1f}s\n")

    daily = (
        enriched.groupBy("day_ist", "source_type")
        .agg(
            F.count("*").alias("documents"),
            F.countDistinct("city").alias("distinct_cities"),
            F.sum(F.col("is_noise").cast("int")).alias("noise_documents"),
            F.sum(F.col("has_media").cast("int")).alias("with_media"),
        )
        .withColumn(
            "noise_rate", F.round(F.col("noise_documents") / F.col("documents"), 4)
        )
        .orderBy("day_ist", "source_type")
    )

    hourly = (
        enriched.groupBy("hour_ist")
        .agg(F.count("*").alias("documents"))
        .orderBy("hour_ist")
    )

    by_city = (
        enriched.filter(F.col("city").isNotNull())
        .groupBy("city")
        .agg(
            F.count("*").alias("documents"),
            F.countDistinct("source_type").alias("source_types"),
        )
        .orderBy(F.desc("documents"))
    )

    # `is_noise` was added to the generator partway through the project, so
    # documents collected before that read as noise_rate 0.0 — absence of the
    # marker, not absence of noise. Only days after the marker landed are
    # comparable.
    print("── intake by day and source type ──")
    print("   (noise_rate is only meaningful for days after the is_noise marker was added)")
    daily.show(20, truncate=False)
    print("── top cities by document volume ──")
    by_city.show(10, truncate=False)

    # Deliberately NOT called a diurnal weather pattern. This buckets
    # `collected_at`, so it measures when the collector was *running* — on a
    # prototype that is developer working hours, not climatology. It is still
    # worth reporting, as the operational question "when were we blind?", and
    # the empty hours below are the answer.
    peak = hourly.orderBy(F.desc("documents")).first()
    covered = hourly.filter(F.col("documents") > 0).count()
    if peak:
        print(
            f"── ingest coverage: {covered}/24 IST hours have data; "
            f"busiest {peak['hour_ist']:02d}:00 ({peak['documents']:,} docs) ──"
        )
        print(
            "   (this is collector uptime, not a weather cycle — hazard "
            "time-of-day lives in the preparedness endpoint, which buckets "
            "event time rather than ingest time)\n"
        )

    for name, df in (("intake_daily", daily), ("intake_hourly", hourly), ("intake_by_city", by_city)):
        df.coalesce(1).write.mode("overwrite").parquet(f"{out_path}/{name}")
    print(f"wrote 3 Parquet aggregates to {out_path}\n")

    # Reconcile against the serving database. The lake is the record; a
    # mismatch means the derived view drifted, and it is better to see that
    # here than to trust a dashboard that quietly disagrees with its source.
    try:
        import subprocess

        db_total = int(
            subprocess.run(
                ["psql", "-d", "weather", "-tAc", "select count(*) from raw_events"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            ).stdout.strip()
        )
        delta = total - db_total
        print("── reconcile: lake vs serving database ──")
        print(f"  lake documents : {total:,}")
        print(f"  raw_events rows: {db_total:,}")
        if delta == 0:
            print("  MATCH\n")
        else:
            print(f"  DELTA {delta:+,} — expected while the backend writes to one backend only\n")
    except Exception as exc:
        print(f"(reconcile skipped: {exc})\n")

    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
