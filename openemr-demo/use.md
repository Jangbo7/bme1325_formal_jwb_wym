docker compose up -d
docker compose ps
docker compose logs -f openemr
http://localhost:8080
Username: admin
Password: pass
docker compose down
<!-- 删除数据↓ -->
docker compose down -v