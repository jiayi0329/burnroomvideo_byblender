# 兼容发布路径

实现已迁入[deploy](../deploy/README.md)。继续使用`release/scripts/build.ps1`、`deploy.ps1`及`release/out/`；旧脚本只转调新实现。生产/GPU模板、prod.env.example和prepare_deploy.sh为字节一致的兼容副本，禁止单独改出两个版本。没有真实凭证随此目录提交。

本轮只进行离线测试，没有部署；不要因目录整理而重建容器或改写历史任务。
