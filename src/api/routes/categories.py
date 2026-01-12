"""Categories API routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from src.api.dependencies import get_db
from src.api.middleware.error_handler import NotFoundError
from src.api.schemas.common import PaginatedResponse, PaginationMeta, CategoryInfo
from src.models.database import Category, Product

router = APIRouter(prefix="/categories", tags=["Categories"])


class CategoryResponse(CategoryInfo):
    """Category response with additional fields."""

    source_app: str
    external_id: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    is_active: bool = True
    products_count: int = 0

    class Config:
        from_attributes = True


class CategoryTree(CategoryResponse):
    """Category with children for tree view."""

    children: List["CategoryTree"] = []


def build_category_response(category: Category, products_count: int = 0) -> CategoryResponse:
    """Build category response from ORM model."""
    return CategoryResponse(
        id=category.id,
        name=category.name,
        name_ar=category.name_ar,
        image_url=category.image_url,
        source_app=category.source_app,
        external_id=category.external_id,
        parent_id=category.parent_id,
        sort_order=category.sort_order,
        is_active=category.is_active,
        products_count=products_count,
    )


@router.get("", response_model=PaginatedResponse[CategoryResponse])
async def list_categories(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    parent_id: Optional[int] = Query(None, description="Filter by parent ID"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
):
    """List categories with pagination."""
    query = db.query(Category)

    if source_app:
        query = query.filter(Category.source_app == source_app)
    if parent_id is not None:
        query = query.filter(Category.parent_id == parent_id)
    elif parent_id is None and source_app:
        # By default, show only root categories when filtering by app
        pass
    if is_active is not None:
        query = query.filter(Category.is_active == is_active)

    total = query.count()

    offset = (page - 1) * per_page
    categories = (
        query
        .order_by(Category.sort_order, Category.name)
        .offset(offset)
        .limit(per_page)
        .all()
    )

    # Get product counts
    category_ids = [c.id for c in categories]
    product_counts = dict(
        db.query(Product.category_id, func.count(Product.id))
        .filter(Product.category_id.in_(category_ids))
        .group_by(Product.category_id)
        .all()
    )

    items = [
        build_category_response(c, product_counts.get(c.id, 0))
        for c in categories
    ]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse(data=items, meta=meta)


@router.get("/tree")
async def get_categories_tree(
    source_app: Optional[str] = Query(None, description="Filter by source app"),
    db: Session = Depends(get_db),
) -> List[CategoryTree]:
    """Get categories as hierarchical tree."""
    query = db.query(Category)
    if source_app:
        query = query.filter(Category.source_app == source_app)

    categories = query.order_by(Category.sort_order, Category.name).all()

    # Get product counts for all categories
    category_ids = [c.id for c in categories]
    product_counts = dict(
        db.query(Product.category_id, func.count(Product.id))
        .filter(Product.category_id.in_(category_ids))
        .group_by(Product.category_id)
        .all()
    ) if category_ids else {}

    # Build tree structure
    category_map = {}
    roots = []

    for cat in categories:
        tree_item = CategoryTree(
            id=cat.id,
            name=cat.name,
            name_ar=cat.name_ar,
            image_url=cat.image_url,
            source_app=cat.source_app,
            external_id=cat.external_id,
            parent_id=cat.parent_id,
            sort_order=cat.sort_order,
            is_active=cat.is_active,
            products_count=product_counts.get(cat.id, 0),
            children=[],
        )
        category_map[cat.id] = tree_item

    for cat in categories:
        tree_item = category_map[cat.id]
        if cat.parent_id and cat.parent_id in category_map:
            category_map[cat.parent_id].children.append(tree_item)
        else:
            roots.append(tree_item)

    return roots


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: int,
    db: Session = Depends(get_db),
):
    """Get category details by ID."""
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise NotFoundError("Category", category_id)

    # Get product count
    products_count = (
        db.query(func.count(Product.id))
        .filter(Product.category_id == category_id)
        .scalar()
    )

    return build_category_response(category, products_count)


@router.get("/{category_id}/products")
async def get_category_products(
    category_id: int,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get products in a category."""
    from src.api.routes.products import build_product_summary, ProductSummary

    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise NotFoundError("Category", category_id)

    query = db.query(Product).options(
        joinedload(Product.category),
        joinedload(Product.brand_rel),
        joinedload(Product.price_records),
        joinedload(Product.units),
    ).filter(Product.category_id == category_id)

    total = query.count()

    offset = (page - 1) * per_page
    products = (
        query
        .order_by(Product.name)
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = [build_product_summary(p) for p in products]
    meta = PaginationMeta.from_pagination(total, page, per_page)

    return PaginatedResponse[ProductSummary](data=items, meta=meta)
