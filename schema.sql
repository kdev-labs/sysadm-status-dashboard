CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_name TEXT NOT NULL,
    last_updated DATETIME NOT NULL,
    last_action TEXT NOT NULL,
    hosts TEXT,
    has_current INTEGER,
    has_new INTEGER,
    has_old INTEGER,
    git_tag TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(binary_name)
);

CREATE TABLE IF NOT EXISTS release_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    binary_name TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    action TEXT NOT NULL,
    hosts TEXT,
    source_size INTEGER,
    source_path TEXT,
    operation TEXT,
    git_tag TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (binary_name) REFERENCES releases(binary_name)
);

CREATE TABLE IF NOT EXISTS playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_name TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    status TEXT NOT NULL,
    hosts TEXT NOT NULL,
    details TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(playbook_name)
);

CREATE TABLE IF NOT EXISTS file_hashes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path)
);

CREATE INDEX IF NOT EXISTS idx_file_path_hash ON file_hashes(file_path, file_hash);
CREATE INDEX IF NOT EXISTS idx_release_history_binary ON release_history(binary_name);
CREATE INDEX IF NOT EXISTS idx_release_history_timestamp ON release_history(timestamp);
