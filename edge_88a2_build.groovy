pipeline {
    agent any
    options {
        timestamps()               // 日志带时间戳
        disableConcurrentBuilds()  // 同一任务禁止并发，避免 workspace 冲突
    }
    stages {
        stage('repo 拉取代码') {
            steps {
                sh '''
                    #!/bin/bash
                    set -e
                    if [ ! -d .repo ]; then
                        repo init -u https://github.com/sophgo/manifest.git -m release/all_repos.xml
                    fi
                    repo sync -j8
                '''
            }
        }
        stage('编译 edge_wevb_emmc') {
            steps {
                sh '''
                    #!/bin/bash
                    set -e
                    source build/envsetup_soc.sh
                    defconfig edge_wevb_emmc
                    clean_edge_all && build_edge_all
                '''
            }
        }
        stage('归档固件') {
            steps {
                // 编译产物归档到 Jenkins，网页上可直接下载
                archiveArtifacts artifacts: 'install/soc_edge_wevb_emmc/**/*.img, install/soc_edge_wevb_emmc/**/*.zip',
                                 allowEmptyArchive: true
            }
        }
    }
    post {
        success { echo '✅ 编译成功，产物见本页 Artifacts' }
        failure { echo '❌ 编译失败，点 Console Output 查看日志' }
    }
}

