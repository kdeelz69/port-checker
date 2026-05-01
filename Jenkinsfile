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
        sh """
          set -eu
          params.DEPLOY_DIR="${params.DEPLOY_DIR}"
          if ! mkdir -p "${params.DEPLOY_DIR}" 2>/dev/null; then
            params.DEPLOY_DIR="${WORKSPACE}/.deploy"
            mkdir -p "${params.DEPLOY_DIR}"
            echo "DEPLOY_DIR not writable. Falling back to ${params.DEPLOY_DIR}"
          fi
          printf '%s' "${params.DEPLOY_DIR}" > .deploy_dir_path
          rsync -a --delete --exclude ".git" --exclude ".venv" ./ "${params.DEPLOY_DIR}/"
        """
      }
    }

    stage('Deploy') {
      steps {
        sh """
          set -eu
          params.DEPLOY_DIR="\$(cat .deploy_dir_path)"
          cd "${params.DEPLOY_DIR}"

          if docker compose version >/dev/null 2>&1; then
            docker compose up -d --build
          elif command -v docker-compose >/dev/null 2>&1; then
            docker-compose up -d --build
          else
            echo "Docker Compose is not available."
            exit 1
          fi
        """
      }
    }

    stage('Smoke Test') {
      steps {
        sh """
          set -eu
          sleep 10
          curl -fsS "http://127.0.0.1:${params.APP_PORT}/api/system-health"
        """
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
