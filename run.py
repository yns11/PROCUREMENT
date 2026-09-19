"""Databricks assigns the listening port. Production configuration fails closed."""
import os
import uvicorn
if __name__=='__main__':
    uvicorn.run('procurement.api:app',host='0.0.0.0',port=int(os.getenv('DATABRICKS_APP_PORT','8000')),proxy_headers=False)
