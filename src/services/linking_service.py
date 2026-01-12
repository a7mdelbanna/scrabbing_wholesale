"""Product linking service for cross-app product matching."""
import re
from typing import List, Optional, Tuple, Dict, Any, Set
from datetime import datetime
from difflib import SequenceMatcher
from collections import Counter

from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from src.models.database import Product, ProductLink, PriceRecord, ProductUnit


# Arabic stopwords to ignore in matching
ARABIC_STOPWORDS = {'من', 'في', 'على', 'مع', 'عن', 'إلى', 'و', 'ب', 'ال', 'جم', 'جرام', 'مل', 'لتر', 'كجم', 'ك', 'قطعة', 'علبة', 'كرتونة', 'حبة'}
ENGLISH_STOPWORDS = {'the', 'a', 'an', 'of', 'and', 'or', 'with', 'for', 'in', 'to', 'g', 'gm', 'ml', 'l', 'kg', 'pcs', 'pack'}


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

    def find_matches_for_product(
        self,
        product_id: int,
        target_app: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Find top matching products in a target app for a given product.
        Uses multiple matching strategies: barcode, SKU, name tokens, brand+name.

        Args:
            product_id: Source product ID
            target_app: Target app to search in
            limit: Maximum matches to return

        Returns:
            List of matching products with scores and match reasons
        """
        product = self.db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return []

        # Get all products from target app
        target_products = self.db.query(Product).filter(
            Product.source_app == target_app,
            Product.is_active == True,
        ).all()

        matches = []
        for target in target_products:
            # Skip if already linked
            if self._get_existing_link(product.id, target.id):
                continue

            score, reasons = self._multi_strategy_match(product, target)
            if score > 0.3:  # Minimum threshold
                # Get latest price
                latest_price = self.db.query(PriceRecord).filter(
                    PriceRecord.product_id == target.id
                ).order_by(PriceRecord.recorded_at.desc()).first()

                matches.append({
                    "product_id": target.id,
                    "name": target.name,
                    "name_ar": target.name_ar,
                    "barcode": target.barcode,
                    "sku": target.sku,
                    "image_url": target.image_url,
                    "price": float(latest_price.price) if latest_price else None,
                    "is_available": latest_price.is_available if latest_price else True,
                    "score": round(score, 4),
                    "match_reasons": reasons,
                    "match_type": self._get_primary_match_type(reasons),
                })

        # Sort by score and return top matches
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches[:limit]

    def _multi_strategy_match(self, product_a: Product, product_b: Product) -> Tuple[float, List[str]]:
        """
        Match products using multiple strategies.
        Returns (score, list of reasons).
        """
        scores = []
        reasons = []

        # Strategy 1: Exact barcode match (highest confidence)
        if product_a.barcode and product_b.barcode:
            if product_a.barcode.strip() == product_b.barcode.strip():
                return (1.0, ["Exact barcode match"])

        # Strategy 2: SKU match
        if product_a.sku and product_b.sku:
            sku_a = product_a.sku.strip().lower()
            sku_b = product_b.sku.strip().lower()
            if sku_a == sku_b:
                scores.append(0.95)
                reasons.append("Exact SKU match")
            elif SequenceMatcher(None, sku_a, sku_b).ratio() > 0.8:
                sku_sim = SequenceMatcher(None, sku_a, sku_b).ratio()
                scores.append(sku_sim * 0.8)
                reasons.append(f"Similar SKU ({sku_sim:.0%})")

        # Strategy 3: Token-based name matching
        tokens_a = self._tokenize_name(product_a.name or "")
        tokens_b = self._tokenize_name(product_b.name or "")

        if tokens_a and tokens_b:
            # Jaccard similarity on tokens
            intersection = len(tokens_a & tokens_b)
            union = len(tokens_a | tokens_b)
            if union > 0:
                jaccard = intersection / union
                if jaccard > 0.5:
                    scores.append(jaccard * 0.85)
                    common = tokens_a & tokens_b
                    reasons.append(f"Common words: {', '.join(list(common)[:3])}")

        # Strategy 4: Sequence matching on normalized names
        name_a = self._normalize_name(product_a.name or "")
        name_b = self._normalize_name(product_b.name or "")
        if name_a and name_b:
            name_sim = SequenceMatcher(None, name_a, name_b).ratio()
            if name_sim > 0.6:
                scores.append(name_sim * 0.8)
                reasons.append(f"Name similarity ({name_sim:.0%})")

        # Strategy 5: Brand + partial name match
        brand_a = self._extract_brand(product_a)
        brand_b = self._extract_brand(product_b)
        if brand_a and brand_b and brand_a.lower() == brand_b.lower():
            scores.append(0.3)  # Bonus for same brand
            reasons.append(f"Same brand: {brand_a}")

            # If same brand, check partial name overlap
            if name_a and name_b:
                partial_sim = self._partial_match(name_a, name_b)
                if partial_sim > 0.5:
                    scores.append(partial_sim * 0.5)
                    reasons.append(f"Partial name match ({partial_sim:.0%})")

        # Strategy 6: Arabic name matching
        name_ar_a = self._normalize_name(product_a.name_ar or product_a.name or "")
        name_ar_b = self._normalize_name(product_b.name_ar or product_b.name or "")
        if name_ar_a and name_ar_b:
            ar_sim = SequenceMatcher(None, name_ar_a, name_ar_b).ratio()
            if ar_sim > 0.6:
                scores.append(ar_sim * 0.7)
                if "Name similarity" not in str(reasons):
                    reasons.append(f"Arabic name match ({ar_sim:.0%})")

        if not scores:
            return (0.0, [])

        # Calculate weighted average score
        final_score = min(sum(scores) / len(scores) + (len(reasons) * 0.05), 1.0)
        return (final_score, reasons)

    def _tokenize_name(self, name: str) -> Set[str]:
        """Extract meaningful tokens from product name."""
        # Remove size/weight patterns
        name = re.sub(r'\d+\.?\d*\s*(جم|جرام|مل|لتر|كجم|g|gm|ml|l|kg|ك)\b', '', name, flags=re.IGNORECASE)
        # Remove numbers
        name = re.sub(r'\d+', '', name)
        # Split into words
        words = re.findall(r'[\u0600-\u06FF]+|[a-zA-Z]+', name.lower())
        # Remove stopwords and short words
        tokens = {w for w in words if len(w) > 2 and w not in ARABIC_STOPWORDS and w not in ENGLISH_STOPWORDS}
        return tokens

    def _extract_brand(self, product: Product) -> Optional[str]:
        """Extract brand name from product."""
        if product.brand:
            # Handle case where brand is a string instead of Brand object
            if isinstance(product.brand, str):
                return product.brand
            # Brand is an object with name/name_ar attributes
            return getattr(product.brand, 'name', None) or getattr(product.brand, 'name_ar', None)
        return None

    def _partial_match(self, str_a: str, str_b: str) -> float:
        """Check if one string contains significant part of another."""
        shorter = str_a if len(str_a) < len(str_b) else str_b
        longer = str_b if len(str_a) < len(str_b) else str_a

        if shorter in longer:
            return len(shorter) / len(longer)

        # Check word-level containment
        words_shorter = set(shorter.split())
        words_longer = set(longer.split())
        if words_shorter and words_shorter.issubset(words_longer):
            return len(words_shorter) / len(words_longer)

        return 0.0

    def _get_primary_match_type(self, reasons: List[str]) -> str:
        """Determine primary match type from reasons."""
        reasons_str = " ".join(reasons).lower()
        if "barcode" in reasons_str:
            return "barcode"
        if "sku" in reasons_str:
            return "sku"
        if "brand" in reasons_str:
            return "brand"
        if "name" in reasons_str or "word" in reasons_str:
            return "name"
        return "similarity"

    def search_products_in_app(
        self,
        query: str,
        source_app: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for products in a specific app by name.

        Args:
            query: Search query
            source_app: App to search in
            limit: Maximum results

        Returns:
            List of matching products
        """
        search_filter = f"%{query}%"
        products = self.db.query(Product).filter(
            Product.source_app == source_app,
            Product.is_active == True,
            or_(
                Product.name.ilike(search_filter),
                Product.name_ar.ilike(search_filter),
            )
        ).limit(limit).all()

        results = []
        for p in products:
            latest_price = self.db.query(PriceRecord).filter(
                PriceRecord.product_id == p.id
            ).order_by(PriceRecord.recorded_at.desc()).first()

            results.append({
                "product_id": p.id,
                "name": p.name,
                "name_ar": p.name_ar,
                "barcode": p.barcode,
                "sku": p.sku,
                "image_url": p.image_url,
                "price": float(latest_price.price) if latest_price else None,
                "is_available": latest_price.is_available if latest_price else True,
            })

        return results

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

    # ============= Unit-Level Linking Methods =============

    def get_product_units(self, product_id: int) -> List[Dict[str, Any]]:
        """Get all units for a product with their prices."""
        units = self.db.query(ProductUnit).filter(
            ProductUnit.product_id == product_id,
            ProductUnit.is_active == True,
        ).order_by(ProductUnit.factor).all()

        result = []
        for unit in units:
            # Get latest price for this unit
            latest_price = self.db.query(PriceRecord).filter(
                PriceRecord.product_id == product_id,
                PriceRecord.unit_id == unit.id,
            ).order_by(PriceRecord.recorded_at.desc()).first()

            # If no unit-specific price, try product-level price
            if not latest_price:
                latest_price = self.db.query(PriceRecord).filter(
                    PriceRecord.product_id == product_id,
                    PriceRecord.unit_id == None,
                ).order_by(PriceRecord.recorded_at.desc()).first()

            price = float(latest_price.price) if latest_price else None
            result.append({
                "unit_id": unit.id,
                "name": unit.name,
                "name_ar": unit.name_ar,
                "factor": unit.factor,
                "barcode": unit.barcode,
                "is_base_unit": unit.is_base_unit,
                "price": price,
                "price_per_base": round(price / unit.factor, 2) if price and unit.factor else None,
                "is_available": latest_price.is_available if latest_price else True,
            })

        return result

    def find_unit_matches(
        self,
        source_unit_id: int,
        target_product_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Find matching units in target product for a source unit.

        Uses multiple matching strategies:
        1. Unit barcode match (highest confidence)
        2. Factor match (same factor = likely same unit type)
        3. Unit name similarity
        4. Normalized price similarity

        Returns list of units with match scores and reasons.
        """
        source_unit = self.db.query(ProductUnit).filter(ProductUnit.id == source_unit_id).first()
        if not source_unit:
            return []

        # Get source product and price for comparison
        source_product = self.db.query(Product).filter(Product.id == source_unit.product_id).first()
        source_price = self.db.query(PriceRecord).filter(
            PriceRecord.product_id == source_unit.product_id,
            PriceRecord.unit_id == source_unit.id,
        ).order_by(PriceRecord.recorded_at.desc()).first()

        source_price_per_base = None
        if source_price and source_unit.factor:
            source_price_per_base = float(source_price.price) / source_unit.factor

        # Get target product's units
        target_units = self.db.query(ProductUnit).filter(
            ProductUnit.product_id == target_product_id,
            ProductUnit.is_active == True,
        ).all()

        matches = []
        for target_unit in target_units:
            score = 0.0
            reasons = []

            # Strategy 1: Unit barcode match (highest confidence)
            if source_unit.barcode and target_unit.barcode:
                if source_unit.barcode.strip() == target_unit.barcode.strip():
                    score = 1.0
                    reasons.append("Unit barcode match")
                    matches.append(self._build_unit_match_result(
                        target_unit, target_product_id, score, reasons, "barcode"
                    ))
                    continue

            # Strategy 2: Factor match
            if source_unit.factor == target_unit.factor:
                score += 0.4
                reasons.append(f"Same factor ({source_unit.factor})")
            elif source_unit.factor and target_unit.factor:
                # Penalize different factors
                factor_ratio = min(source_unit.factor, target_unit.factor) / max(source_unit.factor, target_unit.factor)
                if factor_ratio > 0.8:
                    score += 0.2
                    reasons.append(f"Similar factor (ratio {factor_ratio:.1%})")

            # Strategy 3: Unit name similarity
            name_a = self._normalize_unit_name(source_unit.name or "")
            name_b = self._normalize_unit_name(target_unit.name or "")
            if name_a and name_b:
                name_sim = SequenceMatcher(None, name_a, name_b).ratio()
                if name_sim > 0.7:
                    score += name_sim * 0.3
                    reasons.append(f"Unit name match ({name_sim:.0%})")

            # Strategy 4: Normalized price similarity
            if source_price_per_base:
                target_price = self.db.query(PriceRecord).filter(
                    PriceRecord.product_id == target_product_id,
                    PriceRecord.unit_id == target_unit.id,
                ).order_by(PriceRecord.recorded_at.desc()).first()

                if target_price and target_unit.factor:
                    target_price_per_base = float(target_price.price) / target_unit.factor
                    if source_price_per_base and target_price_per_base:
                        price_ratio = min(source_price_per_base, target_price_per_base) / max(source_price_per_base, target_price_per_base)
                        if price_ratio > 0.7:
                            score += 0.2
                            reasons.append(f"Similar normalized price (ratio {price_ratio:.0%})")

            if score > 0.3:
                match_type = "factor" if "Same factor" in str(reasons) else "similarity"
                matches.append(self._build_unit_match_result(
                    target_unit, target_product_id, score, reasons, match_type
                ))

        # Sort by score
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches

    def _build_unit_match_result(
        self,
        unit: ProductUnit,
        product_id: int,
        score: float,
        reasons: List[str],
        match_type: str,
    ) -> Dict[str, Any]:
        """Build a unit match result dict."""
        # Get price
        latest_price = self.db.query(PriceRecord).filter(
            PriceRecord.product_id == product_id,
            PriceRecord.unit_id == unit.id,
        ).order_by(PriceRecord.recorded_at.desc()).first()

        price = float(latest_price.price) if latest_price else None
        return {
            "unit_id": unit.id,
            "name": unit.name,
            "name_ar": unit.name_ar,
            "factor": unit.factor,
            "barcode": unit.barcode,
            "price": price,
            "price_per_base": round(price / unit.factor, 2) if price and unit.factor else None,
            "is_available": latest_price.is_available if latest_price else True,
            "score": round(score, 4),
            "match_reasons": reasons,
            "match_type": match_type,
        }

    def _normalize_unit_name(self, name: str) -> str:
        """Normalize unit name for comparison."""
        # Common unit name mappings
        mappings = {
            'كرتونة': 'carton',
            'كرتون': 'carton',
            'علبة': 'box',
            'عبوة': 'pack',
            'قطعة': 'piece',
            'حبة': 'piece',
            'زجاجة': 'bottle',
            'كيس': 'bag',
            'باكيت': 'packet',
            'باكت': 'packet',
            'شريط': 'strip',
        }

        name_lower = name.lower().strip()
        # Replace Arabic with English equivalents
        for ar, en in mappings.items():
            if ar in name_lower:
                name_lower = name_lower.replace(ar, en)

        # Remove numbers
        name_lower = re.sub(r'\d+', '', name_lower)
        return name_lower.strip()

    def create_unit_link(
        self,
        product_a_id: int,
        product_b_id: int,
        unit_a_id: int,
        unit_b_id: int,
        verified_by: Optional[str] = None,
    ) -> ProductLink:
        """
        Create a link between two products at the unit level.

        Args:
            product_a_id: First product ID
            product_b_id: Second product ID
            unit_a_id: Unit ID from first product
            unit_b_id: Unit ID from second product
            verified_by: Name of person creating the link

        Returns:
            The created ProductLink

        Raises:
            ValueError: If products/units don't exist or validation fails
        """
        # Validate products exist
        product_a = self.db.query(Product).filter(Product.id == product_a_id).first()
        product_b = self.db.query(Product).filter(Product.id == product_b_id).first()

        if not product_a or not product_b:
            raise ValueError("One or both products not found")

        if product_a.source_app == product_b.source_app:
            raise ValueError("Cannot link products from the same app")

        # Validate units exist and belong to correct products
        unit_a = self.db.query(ProductUnit).filter(
            ProductUnit.id == unit_a_id,
            ProductUnit.product_id == product_a_id,
        ).first()
        unit_b = self.db.query(ProductUnit).filter(
            ProductUnit.id == unit_b_id,
            ProductUnit.product_id == product_b_id,
        ).first()

        if not unit_a or not unit_b:
            raise ValueError("One or both units not found or don't belong to specified products")

        # Check for existing link (at unit level)
        existing = self._get_existing_unit_link(product_a_id, product_b_id, unit_a_id, unit_b_id)
        if existing:
            raise ValueError("Link already exists between these units")

        # Ensure consistent ordering (smaller product_id first)
        if product_a_id > product_b_id:
            product_a_id, product_b_id = product_b_id, product_a_id
            unit_a_id, unit_b_id = unit_b_id, unit_a_id

        # Generate match reason
        match_reason = f"Manually linked: {unit_a.name} ({unit_a.factor}x) ↔ {unit_b.name} ({unit_b.factor}x)"

        # Warn if factors are significantly different
        link_type = "manual"
        if unit_a.factor and unit_b.factor:
            factor_ratio = min(unit_a.factor, unit_b.factor) / max(unit_a.factor, unit_b.factor)
            if factor_ratio < 0.5:
                match_reason += f" [WARNING: Factor mismatch - {unit_a.factor} vs {unit_b.factor}]"
                link_type = "manual_warning"

        link = ProductLink(
            product_a_id=product_a_id,
            product_b_id=product_b_id,
            unit_a_id=unit_a_id,
            unit_b_id=unit_b_id,
            link_type=link_type,
            confidence_score=1.0,
            match_reason=match_reason,
            verified_by=verified_by,
            verified_at=datetime.utcnow() if verified_by else None,
            is_active=True,
        )
        self.db.add(link)
        self.db.commit()
        self.db.refresh(link)
        return link

    def _get_existing_unit_link(
        self,
        product_a_id: int,
        product_b_id: int,
        unit_a_id: int,
        unit_b_id: int,
    ) -> Optional[ProductLink]:
        """Check if a unit-level link already exists."""
        min_pid = min(product_a_id, product_b_id)
        max_pid = max(product_a_id, product_b_id)

        # Swap units if products were swapped
        if product_a_id > product_b_id:
            unit_a_id, unit_b_id = unit_b_id, unit_a_id

        return self.db.query(ProductLink).filter(
            ProductLink.product_a_id == min_pid,
            ProductLink.product_b_id == max_pid,
            ProductLink.unit_a_id == unit_a_id,
            ProductLink.unit_b_id == unit_b_id,
        ).first()

    def get_unit_link_suggestions(
        self,
        product_a_id: int,
        product_b_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Get suggested unit-to-unit links between two products.

        Returns pairs of units that should be linked based on:
        - Barcode matches
        - Factor matches
        - Name similarity
        - Price similarity (normalized)
        """
        units_a = self.db.query(ProductUnit).filter(
            ProductUnit.product_id == product_a_id,
            ProductUnit.is_active == True,
        ).all()

        units_b = self.db.query(ProductUnit).filter(
            ProductUnit.product_id == product_b_id,
            ProductUnit.is_active == True,
        ).all()

        suggestions = []

        for unit_a in units_a:
            matches = self.find_unit_matches(unit_a.id, product_b_id)
            for match in matches:
                # Check if this link already exists
                existing = self._get_existing_unit_link(
                    product_a_id, product_b_id, unit_a.id, match["unit_id"]
                )
                if existing:
                    continue

                # Get unit_a price
                price_a = self.db.query(PriceRecord).filter(
                    PriceRecord.product_id == product_a_id,
                    PriceRecord.unit_id == unit_a.id,
                ).order_by(PriceRecord.recorded_at.desc()).first()

                price_a_val = float(price_a.price) if price_a else None
                price_per_base_a = round(price_a_val / unit_a.factor, 2) if price_a_val and unit_a.factor else None

                suggestions.append({
                    "unit_a": {
                        "unit_id": unit_a.id,
                        "name": unit_a.name,
                        "factor": unit_a.factor,
                        "barcode": unit_a.barcode,
                        "price": price_a_val,
                        "price_per_base": price_per_base_a,
                    },
                    "unit_b": {
                        "unit_id": match["unit_id"],
                        "name": match["name"],
                        "factor": match["factor"],
                        "barcode": match["barcode"],
                        "price": match["price"],
                        "price_per_base": match["price_per_base"],
                    },
                    "score": match["score"],
                    "match_reasons": match["match_reasons"],
                    "match_type": match["match_type"],
                    "factor_warning": unit_a.factor != match["factor"] if unit_a.factor and match["factor"] else False,
                })

        # Sort by score
        suggestions.sort(key=lambda x: x["score"], reverse=True)
        return suggestions
