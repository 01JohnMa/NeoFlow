pipeline {
    agent { label '10.10.80.37' }

    environment {
        // Gitea 配置
        GITEA_URL = 'http://10.10.80.35:3000/root/neoflow.git'
        GITEA_BRANCH = 'develop'

        // Nexus 配置
        NEXUS_URL = 'http://10.10.80.35:8081'
        NEXUS_REGISTRY = '10.10.80.35:8082'
        NEXUS_USERNAME = 'admin'
        NEXUS_PASSWORD = '123456'

        // 目标服务器配置
        DEPLOY_SERVER = '10.10.80.37'
        DEPLOY_USER = 'caigou'
        DEPLOY_PATH = '/opt/neoflow'
    }

    stages {
        stage('准备环境') {
            steps {
                echo '=========================================='
                echo '开始构建流程'
                echo "构建编号: ${BUILD_NUMBER}"
                echo '=========================================='
            }
        }

        stage('拉取代码') {
            steps {
                echo '从 Gitea 拉取代码...'
                git branch: "${GITEA_BRANCH}",
                    credentialsId: 'gitea-credentials',
                    url: "${GITEA_URL}"
                echo '代码拉取完成'
            }
        }

        stage('同步代码到目标目录') {
            steps {
                echo '同步代码到部署目录...'
                sh """
                    set -e
                    # 检查目标目录是否为 git 仓库
                    if [ -d "${DEPLOY_PATH}/.git" ]; then
                        echo '目标目录已是 Git 仓库，执行 git pull...'
                        cd ${DEPLOY_PATH}
                        git pull origin ${GITEA_BRANCH}
                    else
                        echo '克隆代码到目标目录...'
                        rm -rf ${DEPLOY_PATH}
                        git clone ${GITEA_URL} ${DEPLOY_PATH}
                        cd ${DEPLOY_PATH}
                        git checkout ${GITEA_BRANCH}
                    fi
                    echo '代码同步完成'
                """
            }
        }

        stage('构建 Docker 镜像') {
            steps {
                echo '构建 Docker 镜像...'
                sh """
                    docker build -f Dockerfile.api -t ${NEXUS_REGISTRY}/neoflow-api:\${BUILD_NUMBER} .
                    docker build -f web/Dockerfile -t ${NEXUS_REGISTRY}/neoflow-web:\${BUILD_NUMBER} .
                    echo '镜像构建完成'
                """
            }
        }

        stage('推送镜像到 Nexus') {
            steps {
                echo '推送镜像到 Nexus...'
                sh """
                    docker login ${NEXUS_REGISTRY} -u ${NEXUS_USERNAME} -p ${NEXUS_PASSWORD}
                    docker push ${NEXUS_REGISTRY}/neoflow-api:\${BUILD_NUMBER}
                    docker push ${NEXUS_REGISTRY}/neoflow-web:\${BUILD_NUMBER}
                    docker tag ${NEXUS_REGISTRY}/neoflow-api:\${BUILD_NUMBER} ${NEXUS_REGISTRY}/neoflow-api:latest
                    docker tag ${NEXUS_REGISTRY}/neoflow-web:\${BUILD_NUMBER} ${NEXUS_REGISTRY}/neoflow-web:latest
                    docker push ${NEXUS_REGISTRY}/neoflow-api:latest
                    docker push ${NEXUS_REGISTRY}/neoflow-web:latest
                    echo '镜像推送完成'
                """
            }
        }

        stage('部署到目标服务器') {
            steps {
                echo '在本地节点部署...'
                sh """
                    set -e
                    cd ${DEPLOY_PATH}

                    echo '停止旧容器...'
                    docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml stop || true

                    echo '启动新容器...'
                    docker compose -f supabase/docker-compose.yml -f docker-compose.prod.yml up -d

                    echo '清理旧镜像...'
                    docker image prune -f

                    echo '=========================================='
                    echo '部署完成！构建编号: \${BUILD_NUMBER}'
                    echo '=========================================='
                """
            }
        }
    }

    post {
        always {
            cleanWs()
            echo '清理工作目录'
        }
        success {
            echo '=========================================='
            echo '构建和部署成功！'
            echo "构建编号: ${BUILD_NUMBER}"
            echo '=========================================='
        }
        failure {
            echo '=========================================='
            echo '构建或部署失败，请检查日志！'
            echo '=========================================='
        }
    }
}
