"""Test all imports for circular dependencies and correctness."""

import sys
import io

# Fix encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

print('Testing imports...')
try:
    print('1. Importing audit_session...')
    from audit_session import AuditSession, AuditState, create_session, get_session
    print('   OK - audit_session')

    print('2. Importing photo_validator...')
    from photo_validator import PhotoValidator
    print('   OK - photo_validator')

    print('3. Importing audit_database...')
    from audit_database import save_audit_to_database, determine_severity
    print('   OK - audit_database')

    print('4. Importing audit_handlers...')
    from audit_handlers import AuditConversationHandler
    print('   OK - audit_handlers')

    print('5. Importing models...')
    from models import WhatsAppPayload, Reporte, Gestion, Severidad
    print('   OK - models')

    print('6. Importing supabase_manager...')
    from supabase_manager import SupabaseManager
    print('   OK - supabase_manager')

    print('7. Importing meta_client...')
    from meta_client import MetaClient
    print('   OK - meta_client')

    print('\n✅ ALL IMPORTS SUCCESSFUL')
    print('✅ NO CIRCULAR DEPENDENCIES')
    print('✅ READY FOR TESTING')

except Exception as e:
    print(f'\nERROR: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
