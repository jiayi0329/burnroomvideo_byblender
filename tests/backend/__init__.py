"""Backend/catalog/offline HTTP tests. Real database integration is excluded."""
MODULES = (
    'tests.backend.test_room_database', 'tests.backend.test_room_api', 'tests.backend.test_v6_share',
    'tests.backend.test_catalog_deployment', 'tests.backend.test_backend_migration',
    'tests.backend.test_operation_logging',
)
