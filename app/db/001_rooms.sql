CREATE TABLE scenes (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scene_code text NOT NULL UNIQUE, name text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE layout_versions (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scene_id bigint NOT NULL REFERENCES scenes(id),
 fingerprint text NOT NULL, transform jsonb NOT NULL,
 review jsonb NOT NULL, xy_verified boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(scene_id, fingerprint), UNIQUE(id, scene_id)
);
CREATE TABLE rooms (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scene_id bigint NOT NULL, layout_version_id bigint NOT NULL,
 source_room_id text NOT NULL, name text NOT NULL,
 polygon jsonb NOT NULL, area_m2 double precision NOT NULL CHECK(area_m2 >= 0),
 is_valid boolean NOT NULL, problems jsonb NOT NULL,
 FOREIGN KEY(layout_version_id, scene_id) REFERENCES layout_versions(id, scene_id),
 UNIQUE(layout_version_id, source_room_id), UNIQUE(id, layout_version_id, scene_id),
 UNIQUE(id, scene_id)
);
CREATE TABLE points (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scene_id bigint NOT NULL REFERENCES scenes(id), device integer NOT NULL,
 x double precision NOT NULL, y double precision NOT NULL, z double precision NOT NULL,
 UNIQUE(scene_id, device), UNIQUE(id, scene_id)
);
CREATE TABLE point_room_memberships (
 scene_id bigint NOT NULL, point_id bigint NOT NULL, layout_version_id bigint NOT NULL,
 algorithm_status text NOT NULL CHECK(algorithm_status IN ('interior','boundary','outside','overlap')),
 algorithm_room_id bigint, reviewed_room_id bigint,
 review_kind text CHECK(review_kind IN ('interior','doorway','outside','unassigned')),
 review jsonb NOT NULL DEFAULT '{}'::jsonb,
 PRIMARY KEY(point_id, layout_version_id),
 FOREIGN KEY(point_id, scene_id) REFERENCES points(id, scene_id),
 FOREIGN KEY(layout_version_id, scene_id) REFERENCES layout_versions(id, scene_id),
 FOREIGN KEY(algorithm_room_id, layout_version_id, scene_id) REFERENCES rooms(id, layout_version_id, scene_id),
 FOREIGN KEY(reviewed_room_id, layout_version_id, scene_id) REFERENCES rooms(id, layout_version_id, scene_id),
 CHECK (CASE WHEN review_kind IS NULL THEN reviewed_room_id IS NULL
        WHEN review_kind IN ('interior','doorway') THEN reviewed_room_id IS NOT NULL
        ELSE reviewed_room_id IS NULL END)
);
CREATE TABLE assets (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scene_id bigint NOT NULL REFERENCES scenes(id), point_id bigint, room_id bigint,
 kind text NOT NULL, sha256 text NOT NULL, size_bytes bigint NOT NULL CHECK(size_bytes >= 0),
 local_relative_path text NOT NULL, bucket text, object_key text,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(point_id, scene_id) REFERENCES points(id, scene_id),
 FOREIGN KEY(room_id, scene_id) REFERENCES rooms(id, scene_id),
 UNIQUE(scene_id, local_relative_path, sha256), UNIQUE(id, scene_id),
 CHECK((bucket IS NULL) = (object_key IS NULL))
);
CREATE TABLE render_jobs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 scene_id bigint NOT NULL REFERENCES scenes(id), layout_version_id bigint,
 room_id bigint, ignition_point_id bigint, config jsonb NOT NULL DEFAULT '{}'::jsonb,
 status text NOT NULL CHECK(status IN ('unknown','running','done','failed')),
 source text NOT NULL DEFAULT 'file_snapshot', started_at timestamptz, finished_at timestamptz,
 synced_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(layout_version_id, scene_id) REFERENCES layout_versions(id, scene_id),
 FOREIGN KEY(room_id, layout_version_id, scene_id) REFERENCES rooms(id, layout_version_id, scene_id),
 FOREIGN KEY(ignition_point_id, scene_id) REFERENCES points(id, scene_id),
 CHECK(room_id IS NULL OR layout_version_id IS NOT NULL), UNIQUE(id, scene_id)
);
CREATE TABLE render_job_assets (
 scene_id bigint NOT NULL, job_id bigint NOT NULL, asset_id bigint NOT NULL,
 role text NOT NULL CHECK(role IN ('input','output')),
 PRIMARY KEY(job_id, asset_id, role),
 FOREIGN KEY(job_id, scene_id) REFERENCES render_jobs(id, scene_id),
 FOREIGN KEY(asset_id, scene_id) REFERENCES assets(id, scene_id)
);
CREATE INDEX memberships_room ON point_room_memberships(algorithm_room_id);
CREATE INDEX memberships_reviewed_room ON point_room_memberships(reviewed_room_id);
CREATE INDEX assets_point ON assets(point_id);
CREATE INDEX assets_room ON assets(room_id);
CREATE INDEX jobs_scene ON render_jobs(scene_id, id);
