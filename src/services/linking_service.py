"""Product linking service for cross-app product matching."""
import re
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from src.models.database import Product, ProductLink, PriceRecord


class LinkingService:
    """Service for managing product links across apps."""

    def __init__(self, db: Session):
        self.db = db

    def auto_link_by_barcode(self, source_app: Optional[str] = None) -> Dict[str, Any]:
        """
        Automatically link products that share the same barcode across different apps.

        Args:
            source_app: Optional filter to only link products from specific app

        Returns:
            Statistics about links created
        """
        stats = {
            "links_created": 0,
            "links_skipped": 0,
            "products_processed": 0,
            "errors": [],
        }

        # Get all products with barcodes
        query = self.db.query(Product).filter(
            Product.barcode.isnot(None),
            Product.barcode != "",
        )
        if source_app:
            query = query.filter(Product.source_app == source_app)

        products = query.all()
        stats["products_processed"] = len(products)

        # Group products by barcode
        barcode_groups: Dict[str, List[Product]] = {}
        for product in products:
            barcode = product.barcode.strip()
            if barcode:
                if barcode not in barcode_groups:
                    barcode_groups[barcode] = []
                barcode_groups[barcode].append(product)

        # Create links for products with same barcode but different apps
        for barcode, products_list in barcode_groups.items():
            # Get unique apps for this barcode
            apps = set(p.source_app for p in products_list)
            if len(apps) < 2:
                continue  # Need products from at least 2 different apps

            # Create links between products from different apps
            for i, prod_a in enumerate(products_list):
                for prod_b in products_list[i + 1:]:
                    if prod_a.source_app != prod_b.source_app:
                        # Check if link already exists
                        existing = self._get_existing_link(prod_a.id, prod_b.id)
                        if existing:
                            stats["links_skipped"] += 1
                            continue

                        try:
                            link = ProductLink(
                                product_a_id=min(prod_a.id, prod_b.id),
                                product_b_id=max(prod_a.id, prod_b.id),
                                link_type="barcode",
                                confidence_score=1.0,
                                match_reason=f"Matching barcode: {barcode}",
                                is_active=True,
                            )
                            self.db.add(link)
                            stats["links_created"] += 1
                        except Exception as e:
                            stats["errors"].append(str(e))

        self.db.commit()
        return stats

    def _get_existing_link(self, product_a_id: int, product_b_id: int) -> Optional[ProductLink]:
        """Check if a link already exists between two products."""
        min_id = min(product_a_id, product_b_id)
        max_id = max(product_a_id, product_b_id)
        return self.db.query(ProductLink).filter(
            ProductLink.product_a_id == min_id,
            ProductLink.product_b_id == max_id,
        ).first()

    def get_link_suggestions(
        self,
        min_similarity: float = 0.7,
        limit: int = 100,
        source_app: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get suggested product links based on name similarity.

        Args:
            min_similarity: Minimum similarity score (0.0 to 1.0)
            limit: Maximum suggestions to return
            source_app: Optional filter for source app

        Returns:
            List of suggested links with similarity scores
        """
        suggestions = []

        # Get products without barcodes (can't be auto-linked)
        query = self.db.query(Product).filter(
            or_(Product.barcode.is_(None), Product.barcode == "")
        )
        if source_app:
            query = query.filter(Product.source_app == source_app)

        products_no_barcode = query.all()

        # Get all products grouped by app
        all_products = self.db.query(Product).all()
        products_by_app: Dict[str, List[Product]] = {}
        for p in all_products:
            if p.source_app not in products_by_app:
                products_by_app[p.source_app] = []
            products_by_app[p.source_app].append(p)

        # Find similar products across apps
        checked_pairs = set()
        for product in products_no_barcode:
            for other_app, other_products in products_by_app.items():
                if other_app == product.source_app:
                    continue

                for other_product in other_products:
                    # Skip if already checked or linked
                    pair_key = (min(product.id, other_product.id), max(product.id, other_product.id))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    # Check if already linked
                    if self._get_existing_link(product.id, other_product.id):
                        continue

                    # Calculate similarity
                    similarity = self._calculate_similarity(product, other_product)
                    if similarity >= min_similarity:
                        suggestions.append({
                            "product_a_id": product.id,
                            "product_a_name": product.name,
                            "product_a_app": product.source_app,
                            "product_b_id": other_product.id,
                            "product_b_name": other_product.name,
                            "product_b_app": other_product.source_app,
                            "similarity_score": round(similarity, 4),
                            "match_reason": self._get_match_reason(product, other_product, similarity),
                        })

                    if len(suggestions) >= limit:
                        break
                if len(suggestions) >= limit:
                    break
            if len(suggestions) >= limit:
                break

        # Sort by similarity score descending
        suggestions.sort(key=lambda x: x["similarity_score"], reverse=True)
        return suggestions[:limit]

    def _calculate_similarity(self, product_a: Product, product_b: Product) -> float:
        """Calculate similarity between two products based on multiple factors."""
        scores = []

        # Name similarity (Arabic and English)
        name_a = self._normalize_name(product_a.name or "")
        name_b = self._normalize_name(product_b.name or "")
        if name_a and name_b:
            scores.append(SequenceMatcher(None, name_a, name_b).ratio() * 1.5)

        # Arabic name similarity
        name_ar_a = self._normalize_name(product_a.name_ar or "")
        name_ar_b = self._normalize_name(product_b.name_ar or "")
        if name_ar_a and name_ar_b:
            scores.append(SequenceMatcher(None, name_ar_a, name_ar_b).ratio() * 1.5)

        # SKU similarity
        if product_a.sku and product_b.sku:
            sku_sim = SequenceMatcher(None, product_a.sku, product_b.sku).ratio()
            if sku_sim > 0.8:
                scores.append(sku_sim * 2)

        # Same category boost (if both have categories)
        if product_a.category and product_b.category:
            cat_name_a = self._normalize_name(product_a.category.name or "")
            cat_name_b = self._normalize_name(product_b.category.name or "")
            if cat_name_a and cat_name_b:
                cat_sim = SequenceMatcher(None, cat_name_a, cat_name_b).ratio()
                if cat_sim > 0.8:
                    scores.append(0.3)  # Bonus for same category

        if not scores:
            return 0.0

        # Return weighted average, capped at 1.0
        return min(sum(scores) / len(scores), 1.0)

    def _normalize_name(self, name: str) -> str:
        """Normalize product name for comparison."""
        # Remove common size/weight patterns
        name = re.sub(r'\d+\s*(جم|جرام|مل|لتر|كجم|g|gm|ml|l|kg)\b', '', name, flags=re.IGNORECASE)
        # Remove extra whitespace
        name = ' '.join(name.split())
        return name.lower().strip()

    def _get_match_reason(self, product_a: Product, product_b: Product, similarity: float) -> str:
        """Generate a human-readable match reason."""
        reasons = []

        name_sim = SequenceMatcher(
            None,
            self._normalize_name(product_a.name or ""),
            self._normalize_name(product_b.name or "")
        ).ratio()

        if name_sim > 0.8:
            reasons.append(f"High name similarity ({name_sim:.0%})")
        elif name_sim > 0.6:
            reasons.append(f"Name similarity ({name_sim:.0%})")

        if product_a.sku and product_b.sku:
            sku_sim = SequenceMatcher(None, product_a.sku, product_b.sku).ratio()
            if sku_sim > 0.8:
                reasons.append("Similar SKU")

        if product_a.category and product_b.category:
            if product_a.category.name == product_b.category.name:
                reasons.append("Same category")

        return "; ".join(reasons) if reasons else f"Overall similarity: {similarity:.0%}"

    def create_manual_link(
        self,
        product_a_id: int,
        product_b_id: int,
        verified_by: Optional[str] = None,
    ) -> ProductLink:
        """Create a manual link between two products."""
        # Ensure consistent ordering
        min_id = min(product_a_id, product_b_id)
        max_id = max(product_a_id, product_b_id)

        # Check if products exist and are from different apps
        product_a = self.db.query(Product).filter(Product.id == min_id).first()
        product_b = self.db.query(Product).filter(Product.id == max_id).first()

        if not product_a or not product_b:
            raise ValueError("One or both products not found")

        if product_a.source_app == product_b.source_app:
            raise ValueError("Cannot link products from the same app")

        # Check for existing link
        existing = self._get_existing_link(min_id, max_id)
        if existing:
            raise ValueError("Link already exists between these products")

        link = ProductLink(
            product_a_id=min_id,
            product_b_id=max_id,
            link_type="manual",
            confidence_score=1.0,
            match_reason="Manually linked by user",
            verified_by=verified_by,
            verified_at=datetime.utcnow() if verified_by else None,
            is_active=True,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def verify_link(self, link_id: int, verified_by: str) -> ProductLink:
        """Verify a product link."""
        link = self.db.query(ProductLink).filter(ProductLink.id == link_id).first()
        if not link:
            raise ValueError("Link not found")

        link.verified_by = verified_by
        link.verified_at = datetime.utcnow()
        if link.link_type == "suggested":
            link.link_type = "verified"

        self.db.commit()
        self.db.refresh(link)
        return link

    def delete_link(self, link_id: int) -> bool:
        """Delete a product link."""
        link = self.db.query(ProductLink).filter(ProductLink.id == link_id).first()
        if not link:
            return False

        self.db.delete(link)
        self.db.commit()
        return True

    def get_linked_products(self, product_id: int) -> List[Product]:
        """Get all products linked to a given product."""
        links = self.db.query(ProductLink).filter(
            or_(
                ProductLink.product_a_id == product_id,
                ProductLink.product_b_id == product_id,
            ),
            ProductLink.is_active == True,
        ).all()

        linked_ids = set()
        for link in links:
            if link.product_a_id == product_id:
                linked_ids.add(link.product_b_id)
            else:
                linked_ids.add(link.product_a_id)

        if not linked_ids:
            return []

        return self.db.query(Product).filter(Product.id.in_(linked_ids)).all()

    def get_comparison_by_link(self, product_id: int) -> Dict[str, Any]:
        """Get price comparison for a product and all its linked products."""
        # Get the main product
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return {"error": "Product not found"}

        # Get linked products
        linked = self.get_linked_products(product_id)
        all_products = [product] + linked

        # Build comparison data
        comparison_items = []
        prices = []

        for p in all_products:
            # Get latest price
            latest_price = self.db.query(PriceRecord).filter(
                PriceRecord.product_id == p.id
            ).order_by(PriceRecord.recorded_at.desc()).first()

            price = float(latest_price.price) if latest_price else None

            comparison_items.append({
                "product_id": p.id,
                "source_app": p.source_app,
                "name": p.name,
                "name_ar": p.name_ar,
                "barcode": p.barcode,
                "image_url": p.image_url,
                "price": price,
                "original_price": float(latest_price.original_price) if latest_price and latest_price.original_price else None,
                "is_available": latest_price.is_available if latest_price else True,
                "last_updated": latest_price.recorded_at.isoformat() if latest_price else None,
            })

            if price:
                prices.append(price)

        lowest = min(prices) if prices else None
        highest = max(prices) if prices else None

        return {
            "primary_product_id": product_id,
            "primary_name": product.name,
            "barcode": product.barcode,
            "products": comparison_items,
            "lowest_price": lowest,
            "highest_price": highest,
            "price_difference": highest - lowest if lowest and highest else None,
            "apps_count": len(set(p["source_app"] for p in comparison_items)),
        }
