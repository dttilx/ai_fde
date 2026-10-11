# 运维与恢复

数据库备份使用 `pg_dump` 生成私有 `.dump` 文件，媒体对象备份使用 MinIO bucket 的版本化复制或受控文件系统副本。恢复演练必须在隔离数据库和隔离 bucket 中进行，不覆盖生产数据；恢复后检查 migration head、Job 队列、checkpoint、媒体 checksum、权限撤销和诊断报告引用。

`scripts/verify_backup_restore.ps1` 会在隔离环境中用 `pg_restore --list` 校验 dump 可读性，但不会自动覆盖数据库，也不会声称已完成恢复。没有 `APX_BACKUP_DIR`、数据库 dump 或 `pg_restore` 时状态为 `BLOCKED`。真正恢复仍需隔离数据库、媒体 checksum 和权限撤销检查。媒体删除、撤销和签名 URL 失效必须按实际存储策略记录，不能承诺即时撤销。

媒体对象隔离演练可运行 `uv run --project backend python scripts/verify_minio_restore.py`。脚本使用临时 bucket 和自描述 fixture 文件，执行上传、导出、删除、恢复和 checksum 校验，最后删除临时 bucket，不读取或修改 `apx240-media` 生产 bucket。该脚本只证明对象存储链路可恢复，不替代完整现场备份保留、tombstone 和灾备演练。

`verify_backup_restore.ps1` 在主机没有 `pg_restore` 时会自动使用运行中的 PostgreSQL 容器执行只读 `pg_restore --list` 检查；它仍然只验证 dump 可读性，不会覆盖数据库。完整恢复由 `verify_local_database_restore.ps1` 在隔离数据库完成。
