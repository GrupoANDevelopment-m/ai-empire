-- AI Empire initial seed data
-- Run after migrations

-- Default tenant
INSERT INTO tenants (id, name, slug, tier, max_skills, max_tools, max_files, max_file_size, api_calls_per_minute)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Grupo AN',
    'grupo-an',
    'enterprise',
    100,
    1000,
    1000,
    10737418240,
    1000
) ON CONFLICT (slug) DO NOTHING;

-- Default admin user (password: 'empire' - change in production!)
-- bcrypt hash of 'empire' with cost 12
INSERT INTO users (id, tenant_id, email, password_hash, role, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    'admin@empire.local',
    '$2b$12$LQv3c1yqBwEHxv5jK8hZ7OQP5J8Y8ZP5J8Y8ZP5J8Y8ZP5J8Y8ZP5J',
    'admin',
    true
) ON CONFLICT (email) DO NOTHING;

-- Default skills
INSERT INTO skills (id, tenant_id, name, version, source, path, manifest, status)
VALUES
    (gen_random_uuid(), NULL, 'browser-automation', '1.0.0', 'builtin', '.skills/browser-automation',
     '{"name": "browser-automation", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'muapi-studio', '4.0.0', 'builtin', '.skills/muapi-studio',
     '{"name": "muapi-studio", "version": "4.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'saas-b2b', '1.0.0', 'builtin', '.skills/saas-b2b',
     '{"name": "saas-b2b", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'email', '2.0.0', 'builtin', '.skills/email',
     '{"name": "email", "version": "2.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'calendar', '1.0.0', 'builtin', '.skills/calendar',
     '{"name": "calendar", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'crm', '1.0.0', 'builtin', '.skills/crm',
     '{"name": "crm", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'social-media', '1.5.0', 'builtin', '.skills/social-media',
     '{"name": "social-media", "version": "1.5.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'data-analysis', '2.0.0', 'builtin', '.skills/data-analysis',
     '{"name": "data-analysis", "version": "2.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'code-execution', '1.0.0', 'builtin', '.skills/code-execution',
     '{"name": "code-execution", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'web-search', '2.0.0', 'builtin', '.skills/web-search',
     '{"name": "web-search", "version": "2.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'pdf', '1.0.0', 'builtin', '.skills/pdf',
     '{"name": "pdf", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'translation', '1.0.0', 'builtin', '.skills/translation',
     '{"name": "translation", "version": "1.0.0"}', 'installed'),
    (gen_random_uuid(), NULL, 'summarization', '1.0.0', 'builtin', '.skills/summarization',
     '{"name": "summarization", "version": "1.0.0"}', 'installed')
ON CONFLICT DO NOTHING;
