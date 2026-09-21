"""Append an immutable synthetic batch to a dedicated *_demo schema (Spark job)."""

import argparse
import datetime as dt
import re
import uuid
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--seed", default=str(Path(__file__).resolve().parents[2] / "data/seed"))
    args = ap.parse_args()
    if not args.schema.endswith("_demo") or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", x) for x in [args.catalog, args.schema]
    ):
        raise ValueError("Le chargeur de démonstration exige un schéma *_demo et des identifiants SQL simples")
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = SparkSession.builder.getOrCreate()
    batch = "demo-" + uuid.uuid4().hex
    root = Path(__file__).resolve().parents[2]
    ddl = (
        (root / "scripts/uc/create_tables.sql")
        .read_text()
        .replace("${catalog}", args.catalog)
        .replace("${schema}", args.schema)
    )
    ddl = "\n".join(line for line in ddl.splitlines() if not line.strip().startswith("--"))
    for statement in ddl.split(";"):
        if statement.strip():
            spark.sql(statement)
    for path in sorted(Path(args.seed).glob("*.csv")):
        if not re.fullmatch(r"(ref|fct)_[a-z_]+", path.stem):
            continue
        target = f"{args.catalog}.{args.schema}.{path.stem}"
        frame = spark.read.option("header", True).csv(str(path)).withColumn("batch_id", F.lit(batch))
        schema = spark.table(target).schema
        frame.select(*[F.col(f.name).cast(f.dataType).alias(f.name) for f in schema.fields]).write.mode(
            "append"
        ).saveAsTable(target)
    spark.createDataFrame(
        [(batch, dt.datetime.now(dt.timezone.utc), "READY")],
        schema="batch_id string,published_at timestamp,status string",
    ).write.mode("append").saveAsTable(f"{args.catalog}.{args.schema}.erp_batches")
    print("Lot publié :", batch)


if __name__ == "__main__":
    main()
