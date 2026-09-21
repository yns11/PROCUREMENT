"""Data access layer.

* :mod:`procurement_app.data.schemas`   – canonical table schemas shared by all sources
* :mod:`procurement_app.data.sources`   – ERP / reference data sources (local seed CSV, Unity Catalog)
* :mod:`procurement_app.data.store`     – transactional app store (SQLAlchemy: SQLite locally, Lakebase Postgres on Databricks)
* :mod:`procurement_app.data.assembler` – merges ERP data + app entries into an engine :class:`Dataset`
"""
