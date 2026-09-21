"""Deterministic MRP / supply-planning engine.

The engine is pure Python + NumPy and has no dependency on the web layer or on the
data-access layer.  It receives a :class:`~procurement_app.engine.models.Dataset` (plain records) and
:class:`~procurement_app.engine.models.EngineParams` and returns a :class:`~procurement_app.engine.models.MrpResult`.

Modules
-------
calendar    working-day calendar (weekends, holidays, lead-time arithmetic)
models      input / output records and parameters
demand      weekly plan -> daily production -> component demand (BOM explosion)
projection  stock projection, coverage and target stock per article
alerts      alert classification
proposals   net requirement + lot sizing + supplier selection
scenario    what-if events applied on a dataset copy
runner      orchestration for a whole portfolio
"""

from .runner import run_mrp  # noqa: F401
