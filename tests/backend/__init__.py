"""Backend/catalog/offline HTTP tests. Real database integration is excluded."""
MODULES = (
    'test.test_room_database', 'test.test_room_api', 'test.test_v6_share',
    'test.test_catalog_deployment', 'test.test_backend_migration',
)
