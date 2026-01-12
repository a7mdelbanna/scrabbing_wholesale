"""Enumerations used across the application."""
from enum import Enum


class SourceApp(str, Enum):
    """Supported competitor apps."""
    TAGER_ELSAADA = "tager_elsaada"
    BEN_SOLIMAN = "ben_soliman"
    EL_RABIE = "el_rabie"  # شركة الربيع - ZAH CODE
    GOMLA_SHOAIB = "gomla_shoaib"  # جملة شعيب - ZAH CODE


class Currency(str, Enum):
    """Supported currencies."""
    EGP = "EGP"
    USD = "USD"


class UnitType(str, Enum):
    """Product unit types."""
    PIECE = "piece"
    KG = "kg"
    GRAM = "gram"
    LITER = "liter"
    ML = "ml"
    PACK = "pack"
    BOX = "box"
    CARTON = "carton"


class JobStatus(str, Enum):
    """Scrape job statuses."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    """Types of scrape jobs."""
    FULL = "full"
    INCREMENTAL = "incremental"
    CATEGORIES = "categories"
    OFFERS = "offers"


class StockStatus(str, Enum):
    """Product stock statuses."""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    LIMITED = "limited"
    UNKNOWN = "unknown"
