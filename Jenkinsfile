pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  parameters {
    string(name: 'REPO_URL', defaultValue: 'https://github.com/kdeelz69/port-checker.git', description: 'Git repository URL')
    string(name: 'BRANCH', defaultValue: 'main', description: 'Branch to deploy')
    string(name: 'DEPLOY_DIR', defaultValue: '/opt/port-checker', description: 'Target directory on Jenkins host')
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
          rsync -a --delete --exclude '.git' --exclude '.venv' ./ "${DEPLOY_DIR}/"
        '''
      }
    }

    stage('Deploy') {
      steps {
        sh '''
          set -eu
          cd "${DEPLOY_DIR}"

          if docker compose version >/dev/null 2>&1; then
            COMPOSE_CMD="docker compose"
          elif command -v docker-compose >/dev/null 2>&1; then
            COMPOSE_CMD="docker-compose"
          else
            echo "Docker Compose is not available on this Jenkins node."
            exit 1
          fi

          $COMPOSE_CMD up -d --build
        '''
      }
    }

    stage('Smoke Test') {
      steps {
        sh '''
          set -eu
          sleep 6
          curl -fsS "http://127.0.0.1:${APP_PORT}/api/system-health" >/dev/null
        '''
      }
    }
  }

  post {
    success {
      echo "Deployment succeeded."
    }
    failure {
      echo "Deployment failed. Check build logs."
    }
  }
}
