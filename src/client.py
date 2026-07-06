"""XML-RPC client wrapper for Odoo 18.

Reads credentials from an INI file, authenticates against Odoo's XML-RPC
endpoint, and exposes thin wrappers around the ORM methods used by the
migration scripts.
"""
import xmlrpc.client
import configparser


class OdooClient:
    """Connect to Odoo over XML-RPC and expose ORM operations."""

    def __init__(self, config_path: str):
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        self.url = cfg["odoo"]["url"]
        self.db = cfg["odoo"]["db"]
        self.username = cfg["odoo"]["username"]
        self.password = cfg["odoo"]["password"]
        self.uid = None
        self.models = None
        self._connect()

    def _connect(self):
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(
            self.db, self.username, self.password, {}
        )
        if not self.uid:
            raise RuntimeError(
                f"Odoo authentication failed. Check db={self.db}, "
                f"username={self.username}, and password/API key in config."
            )
        self.models = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object"
        )

    def search(self, model: str, domain: list, limit: int = 1):
        """Search records. Returns list of IDs (empty if none)."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "search", [domain], {"limit": limit},
        )

    def create(self, model: str, values: dict) -> int:
        """Create a new record. Returns the new ID."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "create", [values],
        )

    def write(self, model: str, ids: list, values: dict) -> bool:
        """Update existing records by ID. Returns True on success."""
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "write", [ids, values],
        )

    def read(self, model: str, ids: list, fields: list = None):
        """Read field values for given IDs."""
        kwargs = {"fields": fields} if fields else {}
        return self.models.execute_kw(
            self.db, self.uid, self.password,
            model, "read", [ids], kwargs,
        )