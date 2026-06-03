const path = require('path');

const LOG_DIR = path.resolve(__dirname, 'logs');

module.exports = {
  apps: [
    {
      name: 'cpp-chatserver',
      cwd: './bin',
      script: './ChatServer',
      args: '0.0.0.0 6000',
      watch: false,
      autorestart: true,
      out_file: path.join(LOG_DIR, 'cpp-chatserver-out.log'),
      error_file: path.join(LOG_DIR, 'cpp-chatserver-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'java-ai-service',
      cwd: './ai-service',
      script: 'java',
      args: '-Xmx512m -Xms256m -jar target/ai-service-1.0.0.jar',
      watch: false,
      autorestart: true,
      out_file: path.join(LOG_DIR, 'java-ai-service-out.log'),
      error_file: path.join(LOG_DIR, 'java-ai-service-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'python-sandbox',
      cwd: './eruitah-sandbox',
      script: './venv/bin/python3',
      args: '-m uvicorn main:app --host 0.0.0.0 --port 8001',
      interpreter: 'none',
      watch: false,
      autorestart: true,
      out_file: path.join(LOG_DIR, 'python-sandbox-out.log'),
      error_file: path.join(LOG_DIR, 'python-sandbox-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'python-butcanthic',
      cwd: './butcanthic',
      script: './.venv/bin/python3',
      args: '-m uvicorn main:app --host 0.0.0.0 --port 8002',
      interpreter: 'none',
      watch: false,
      autorestart: true,
      env: {
        HF_ENDPOINT: 'https://hf-mirror.com',
        PYTHONUNBUFFERED: '1',
      },
      out_file: path.join(LOG_DIR, 'python-butcanthic-out.log'),
      error_file: path.join(LOG_DIR, 'python-butcanthic-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'vue-frontend',
      cwd: './coding-agent-ui',
      script: 'npm',
      args: 'run dev',
      watch: false,
      autorestart: true,
      out_file: path.join(LOG_DIR, 'vue-frontend-out.log'),
      error_file: path.join(LOG_DIR, 'vue-frontend-error.log'),
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
};
