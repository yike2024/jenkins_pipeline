pipeline {
    agent any
    options {
        timestamps()
        disableConcurrentBuilds()
    }
    stages {
        stage('repo 拉取 SDK 代码') {
            steps {
                dir('sophgo-sdk') {
                    sh '''
                        #!/bin/bash
                        set -e
                            repo init -u https://github.com/sophgo/manifest.git -m development/all_repos.xml
                            # 已有本地仓库：先丢弃所有本地改动，避免 sync 冲突
                            repo forall -j8 -c 'git reset --hard HEAD; git clean -fdx' || true
                    '''
                    // 网络抖动导致失败时自动重试 3 次
                    retry(3) {
                        sh '''
                            #!/bin/bash
                            set -e
                            cd sophgo-sdk
                            repo sync -j8 --force-sync
                        '''
                    }
                }
            }
        }
        stage('编译 edge_wevb_emmc') {
            steps {
                dir('sophgo-sdk') {
                    sh '''
                        #!/bin/bash
                        set -e
                        source build/envsetup_soc.sh
                        defconfig edge_wevb_emmc
                        clean_edge_all && build_edge_all
                    '''
                }
            }
        }
        stage('拷贝产物到 dailybuild') {
            steps {
                sh '''
                    #!/bin/bash
                    set -e
                    TS=$(date +%Y%m%d_%H%M%S)
                    DEST=/dev_dailybuild/edge_wevb_emmc/${TS}
                    mkdir -p "$DEST"
                    cp -rv sophgo-sdk/install/soc_edge_wevb_emmc/. "$DEST"/
                    echo "产物已拷贝到宿主机: /media/cvitek/share/open/github/dev_dailybuild/edge_wevb_emmc/${TS}"
                '''
            }
        }
    }
    post {
        success { echo '✅ 编译成功，产物在 dev_dailybuild/edge_wevb_emmc/ 下以时间戳命名的目录中' }
        failure { echo '❌ 编译失败，点 Console Output 查看日志' }
    }
}

