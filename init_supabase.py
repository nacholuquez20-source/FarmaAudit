"""Initialize Supabase schema on startup."""

import logging
from supabase import create_client, Client
from config import get_settings

logger = logging.getLogger(__name__)

def init_supabase_schema():
    """Create required Supabase tables if they don't exist."""
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_service_key:
        logger.warning("Supabase credentials not configured, skipping schema init")
        return

    try:
        client: Client = create_client(settings.supabase_url, settings.supabase_service_key)

        # Check if webhook_dedup table exists
        try:
            client.table("webhook_dedup").select("*", count="exact").limit(1).execute()
            logger.info("[OK] webhook_dedup table exists")
        except Exception as e:
            if "does not exist" in str(e).lower():
                logger.warning("webhook_dedup table not found, attempting to create...")
                try:
                    # Create webhook_dedup table for message deduplication
                    result = client.rpc("exec_sql", {
                        "sql": """
                        CREATE TABLE IF NOT EXISTS webhook_dedup (
                            message_id TEXT PRIMARY KEY,
                            phone TEXT NOT NULL,
                            claimed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                        );
                        CREATE INDEX IF NOT EXISTS idx_webhook_dedup_claimed_at ON webhook_dedup(claimed_at);
                        """
                    }).execute()
                    logger.info("[OK] webhook_dedup table created")
                except Exception as create_err:
                    logger.error(f"Failed to create webhook_dedup table: {create_err}")
            else:
                logger.error(f"Error checking webhook_dedup table: {e}")

        # Check for other critical tables
        critical_tables = [
            "auditores",
            "sucursales",
            "checklist_perfumeria",
            "conversaciones",
            "sesiones_auditoria",
            "reportes",
            "gestion"
        ]

        for table in critical_tables:
            try:
                client.table(table).select("*", count="exact").limit(1).execute()
                logger.info(f"[OK] {table} table exists")
            except Exception as e:
                if "does not exist" in str(e).lower():
                    logger.error(f"[ERROR] {table} table not found - run supabase_schema.sql manually")
                else:
                    logger.warning(f"[WARN] Could not verify {table}: {e}")

        logger.info("Supabase schema initialization complete")

    except Exception as e:
        logger.error(f"Failed to initialize Supabase schema: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_supabase_schema()
