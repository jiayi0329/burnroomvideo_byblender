#!/usr/bin/env bash
# Run by deploy.ps1 before extraction. No restart, no rendering, no deletion.
set -euo pipefail
umask 077
release_root=$(realpath -e "$1")
current="$release_root/burnroom-deploy-package"
test -f "$current/docker-compose.yml"
cd "$current"

# Refuse to replace a running render's service; stale status needs human review.
python3 - <<'PY'
import json
from pathlib import Path
for path in Path('/data/zhaojy/burnroom-data/app-data').glob('*/render_status.json'):
    if json.loads(path.read_text(encoding='utf-8')).get('status') == 'running':
        raise SystemExit('Render marked running; verify completion before deployment')
PY

stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
backup_dir="/data/zhaojy/burnroom-data/deploy-backups/$stamp"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
container_id=$(docker compose ps -q app-server)
test -n "$container_id"
image_id=$(docker inspect --format '{{.Image}}' "$container_id")
rollback_image="burnroom-app:rollback-$stamp"
docker image tag "$image_id" "$rollback_image"
printf '%s\n' "$rollback_image" > "$backup_dir/image-tag.txt"
printf '%s\n' "$current" > "$backup_dir/deploy-path.txt"
tar --exclude='./data' -czf "$backup_dir/package.tar.gz" -C "$current" .

# Keep existing videos independently of application rollback.
for video in /data/zhaojy/burnroom-data/app-data/*/output.mp4; do
    test -f "$video" || continue
    scene=$(basename "$(dirname "$video")")
    mkdir -p "$backup_dir/videos/$scene"
    cp --reflink=auto --preserve=mode,timestamps "$video" "$backup_dir/videos/$scene/output.mp4"
done
python3 - "$backup_dir" <<'PY'
import hashlib
from pathlib import Path
import sys
root = Path('/data/zhaojy/burnroom-data/app-data')
paths = []
for name in ('mesh.obj', 'points.json', 'timeline.json', 'output.mp4'):
    paths.extend(root.glob('*/' + name))
paths.extend(root.glob('*/diagnostics/alignment/*/review.json'))
with (Path(sys.argv[1]) / 'scene-inputs.sha256').open('w', encoding='utf-8') as out:
    for path in sorted(paths):
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        out.write(f'{digest.hexdigest()}  {path}\n')
PY
services=$(docker compose config --services)
if printf '%s\n' "$services" | awk '$0=="postgres"{found=1} END{exit !found}'; then
    db_container=$(docker compose ps -q postgres)
    if test -n "$db_container"; then
        docker compose exec -T postgres pg_dump -U postgres -d burnroom -Fc > "$backup_dir/database.dump.part"
        mv "$backup_dir/database.dump.part" "$backup_dir/database.dump"
    fi
fi
printf '[predeploy] backup=%s\n[predeploy] rollback_image=%s\n' "$backup_dir" "$rollback_image"
