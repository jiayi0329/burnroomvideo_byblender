# 基础镜像使用 Ubuntu，确保兼容 Blender 的底层图形库
# 基础镜像使用 Ubuntu，确保兼容 Blender 的底层图形库
FROM ubuntu:22.04

# 防止安装过程中弹出交互式时区选择
ENV DEBIAN_FRONTEND=noninteractive

# 替换为阿里云镜像源，解决国内下载超时 502 的问题 (新加的这一行)
RUN sed -i 's/archive.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.aliyun.com/g' /etc/apt/sources.list

# 1. 安装系统依赖：Python 3.11, FFmpeg, 下载工具，以及 Blender 运行必须的 OpenGL 库
RUN apt-get update && apt-get install -y \
    python3.11 python3-pip python3.11-venv \
    ffmpeg wget xz-utils \
    libgl1 libxi6 libxxf86vm1 libxfixes3 libxrender1 \
    libsm6 libice6 libegl1 nvidia-utils-535 \
    && rm -rf /var/lib/apt/lists/*

# 2. 下载并安装 Blender 4.2 LTS
RUN wget https://download.blender.org/release/Blender4.2/blender-4.2.0-linux-x64.tar.xz && \
    tar -xvf blender-4.2.0-linux-x64.tar.xz && \
    mv blender-4.2.0-linux-x64 /usr/local/blender && \
    rm blender-4.2.0-linux-x64.tar.xz
ENV PATH="/usr/local/blender:${PATH}"

# 3. 配置 Python 环境与应用代码
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --default-timeout=100

# 拷贝项目所有文件到容器内
COPY . .

# 启动 FastAPI 后端
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/app"]