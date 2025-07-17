module.exports = {
  apps: [
    {
      name: 'frontend',
      cwd: './',
      script: './.venv/bin/streamlit',
      args: 'run ui_new.py',
      interpreter: '/home/ec2-user/stock-prediction/stock-env/bin/python3',
      watch: false,
    },
    {
      name: 'backend',
      cwd: './',
      script: './.venv/bin/uvicorn',
      args: 'mcp_server:app',
      interpreter: '/home/ec2-user/stock-prediction/stock-env/bin/python3',
      watch: false,
    }
  ]
};

