pipeline {
  agent any

  options {
    timestamps()
    disableConcurrentBuilds()
  }

  parameters {
    string(name: 'REPO_URL', defaultValue: 'https://github.com/kdeelz69/port-checker.git', description: 'Git repository URL')
    string(name: 'BRANCH', defaultValue: 'main', description: 'Branch to deploy')
    string(name: 'SERVER_IP', defaultValue: 'YOUR_SERVER_IP', description: 'Server IP')
    string(name: 'SERVER_USER', defaultValue: 'ubuntu', description: 'SSH user')
    string(name: 'DEPLOY_DIR', defaultValue: '/opt/port-checker', description: 'Directory on server')
    string(name: 'APP_PORT', defaultValue: '5001', description: 'App port')
  }

  stages {
    stage('Checkout') {
      steps {
        git branch: "${params.BRANCH}",
            url: "${params.REPO_URL}",
            credentialsId: 'githubtoken'
      }
    }

    stage('Deploy to Server') {
      steps {
        sshagent(credentials: ['deploy-ssh-key']) {
          sh """
            set -eu

            echo "Creating deploy directory on server..."
            ssh -o StrictHostKeyChecking=no ${params.SERVER_USER}@${params.SERVER_IP} \\
              "mkdir -p ${params.DEPLOY_DIR}"

            echo "Syncing files to server..."
            rsync -avz --delete \\
              --exclude '.git' \\
              --exclude '.venv' \\
              ./ ${params.SERVER_USER}@${params.SERVER_IP}:${params.DEPLOY_DIR}/

            echo "Running Docker Compose on server..."
            ssh -o StrictHostKeyChecking=no ${params.SERVER_USER}@${params.SERVER_IP} \\
              "cd ${params.DEPLOY_DIR} && \\
               if docker compose version >/dev/null 2>&1; then
                 docker compose up -d --build
               elif command -v docker-compose >/dev/null 2>&1; then
                 docker-compose up -d --build
               else
                 echo 'Docker Compose not installed'
                 exit 1
               fi"
          """
        }
      }
    }

    stage('Smoke Test (Server)') {
      steps {
        sh """
          set -eu
          sleep 15
          curl -fsS "http://${params.SERVER_IP}:${params.APP_PORT}/api/system-health"
        """
      }
    }
  }

  post {
    success {
      echo 'Deployment to server succeeded.'
    }
    failure {
      echo 'Deployment failed. Check logs.'
    }
  }
}