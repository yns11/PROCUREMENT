"""Run once with the database owner before deployment; runtime needs only DML."""
import os
from procurement.store import Store
if __name__=='__main__':
    store=Store(os.getenv('DATABASE_URL') or 'lakebase');store.initialize()
    print('Schéma applicatif initialisé.')
