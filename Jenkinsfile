pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  parameters {
    string(name: 'REPO_URL', defaultValue: 'https://github.com/kdeelz69/port-checker.git', description: 'Git repository URL')
    string(name: 'BRANCH', defaultValue: 'main', description: 'Branch to deploy')
    string(name: 'DEPLOY_DIR', defaultValue: '/opt/port-checker', description: 'Target directory inside Jenkins container')
    string(name: 'APP_PORT', defaultValue: '5001', description: 'Published HTTP port from docker-compose.yml')
  }

  stages {
    stage('Checkout') {
      steps {
        git branch: "${params.BRANCH}", url: "${params.REPO_URL}"
      }
    }

    stage('Prepare Deploy Directory') {
      steps {
        sh '''
          set -eu
          mkdir -p "${DEPLOY_DIR}"
          rsync -a --delete --exclude ".git" --exclude ".venv" ./ "${DEPLOY_DIR}/"
        '''
      }
    }

    stage('Deploy') {
      steps {
        sh '''
          set -eu
          cd "${DEPLOY_DIR}"

          if docker compose version >/dev/null 2>&1; then
            docker compose up -d --build
          elif command -v docker-compose >/dev/null 2>&1; then
            docker-compose up -d --build
          else
            echo "Docker Compose is not available."
            exit 1
          fi
        '''
      }
    }

    stage('Smoke Test') {
      steps {
        sh '''
          set -eu
          sleep 10
          curl -fsS "http://127.0.0.1:${APP_PORT}/api/system-health"
        '''
      }
    }
  }

  post {
    success {
      echo "Deployment succeeded."
    }
    failure {
      echo "Deployment failed. Check Console Output."
    }
  }
}