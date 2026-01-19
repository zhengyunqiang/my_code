# 快速启动指南

## ✅ 系统已就绪

数据库已初始化，包含示例数据：
- 管理员账号：`admin` / `admin123`
- 招聘专员：`recruiter` / `recruiter123`
- 示例客户和项目

## 🚀 启动服务

### 方式1：使用启动脚本
```bash
chmod +x scripts/start_dev.sh
./scripts/start_dev.sh
```

### 方式2：手动启动
```bash
# 1. 确保Redis运行
redis-server

# 2. 启动API服务
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式3：使用Docker
```bash
docker-compose up -d
```

## 📖 访问服务

启动后访问：
- API文档：http://localhost:8000/api/docs
- 健康检查：http://localhost:8000/health
- Prometheus指标：http://localhost:8000/metrics

## 🔧 快速测试

### 1. 测试健康检查
```bash
curl http://localhost:8000/health
```

### 2. 创建JD请求
```bash
curl -X POST "http://localhost:8000/api/v1/jd/requests" \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 1,
    "raw_requirement": "我们需要一个Java开发工程师，负责物联网项目开发",
    "created_by": 1
  }'
```

### 3. 分析需求
```bash
# 使用上面返回的request_id
curl "http://localhost:8000/api/v1/jd/requests/{request_id}/analyze"
```

### 4. 生成JD
```bash
curl -X POST "http://localhost:8000/api/v1/jd/requests/{request_id}/generate"
```

## 📝 常见问题

### Q: 如何查看日志？
```bash
tail -f logs/app_*.log
```

### Q: 如何重置数据库？
```bash
python -m database.migrations.init reset
```

### Q: 如何停止服务？
```bash
# 查找进程
ps aux | grep uvicorn

# 停止进程
kill <PID>
```

## 🎯 下一步

1. 访问API文档了解所有接口
2. 尝试上传简历进行智能筛选
3. 探索人才库搜索功能
4. 查看系统监控指标

祝您使用愉快！
