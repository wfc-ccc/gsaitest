/*
 * 高升（GaoSheng）AI 接口自动化测试框架 · Jenkins 声明式流水线
 *
 * 阶段：Checkout -> 环境准备 -> Run API Tests -> Run UI Tests -> Generate Allure Report
 *
 * 前置条件（详见 README「Jenkins 持续集成」章节）：
 *   1. 节点已安装 Python 3.10+ / Google Chrome（UI 用例无头运行）；
 *   2. Jenkins 已安装 Allure 插件（用于发布 HTML 报告）；
 *   3. 已配置 Git 凭证与下述 Secret Text 凭证（AIS_TOKEN / DEEPSEEK_API_KEY）。
 */

pipeline {
    agent any

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 60, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    environment {
        PYTHONUNBUFFERED = '1'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        ALLURE_RESULTS = 'gs_api/report/output/allure_results'
        ALLURE_REPORT  = 'gs_api/report/output/allure_html'
        // 凭证需在 Jenkins 中以 Secret text 类型创建，ID 与下方保持一致
        AIS_TOKEN         = credentials('gaosheng-ais-token')
        DEEPSEEK_API_KEY  = credentials('gaosheng-deepseek-key')
        EMBEDDING_API_KEY = credentials('gaosheng-embedding-key')
    }

    stages {
        stage('Checkout') {
            steps {
                script {
                    // 拉取当前流水线对应的分支/提交
                    def scmVars = checkout scm
                    env.GIT_COMMIT_SHORT = scmVars.GIT_COMMIT ? scmVars.GIT_COMMIT.take(8) : 'unknown'
                    echo "本次构建提交: ${env.GIT_BRANCH} @ ${env.GIT_COMMIT_SHORT}"
                }
            }
        }

        stage('环境准备') {
            steps {
                sh '''
                    set -e
                    python3 -m venv .venv
                    . .venv/bin/activate
                    python -m pip install --upgrade pip
                    pip install -r requirements.txt
                    python -c "import pytest, selenium, allure_pytest; print('依赖安装完成')"
                '''
            }
        }

        stage('Run API Tests') {
            steps {
                sh '''
                    set -e
                    . .venv/bin/activate
                    # 关闭 pytest.ini 中的默认 addopts（含 --clean-alluredir），
                    # 由本阶段显式清理，避免清掉后续 UI 阶段的 Allure 结果
                    rm -rf "${ALLURE_RESULTS}"
                    pytest gs_api/script \
                        -m "smoke and not ui" \
                        -o addopts="" \
                        -v --tb=short \
                        --alluredir="${ALLURE_RESULTS}" \
                        -n auto
                '''
            }
        }

        stage('Run UI Tests') {
            steps {
                sh '''
                    set -e
                    . .venv/bin/activate
                    # --headless：无头模式，无需图形界面；UI 用例串行执行以保证浏览器稳定
                    pytest gs_api/script \
                        -m ui \
                        -o addopts="" \
                        -v --tb=short \
                        --alluredir="${ALLURE_RESULTS}" \
                        --headless
                '''
            }
        }

        stage('Generate Allure Report') {
            steps {
                sh '''
                    set -e
                    if command -v allure >/dev/null 2>&1; then
                        allure generate "${ALLURE_RESULTS}" -o "${ALLURE_REPORT}" --clean
                        echo "Allure HTML 报告已生成: ${ALLURE_REPORT}"
                    else
                        echo "Allure CLI 未安装，将由 Jenkins Allure 插件在 post 阶段生成报告"
                    fi
                '''
            }
        }
    }

    post {
        always {
            // 发布 Allure 报告（需 Jenkins 已安装 Allure 插件）
            allure includeProperties: false, jdk: '', results: [[path: "${ALLURE_RESULTS}"]]
            // 归档 UI 失败截图与生成的 HTML 报告
            archiveArtifacts artifacts: 'gs_api/report/output/screenshots/**/*.png',
                             allowEmptyArchive: true
            archiveArtifacts artifacts: "${ALLURE_REPORT}/**",
                             allowEmptyArchive: true
        }
        failure {
            echo "流水线失败，请查看 Allure 报告与构建日志定位问题。"
        }
        cleanup {
            // 释放无头 Chrome 可能遗留的临时进程/文件
            sh 'rm -rf /tmp/.org.chromium.* || true'
        }
    }
}
