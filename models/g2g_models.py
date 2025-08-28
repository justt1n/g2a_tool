from typing import List, Optional, Dict

from pydantic import BaseModel, Field


class PriceInfo(BaseModel):
    country_code: str = Field(..., alias='countryCode')
    currency_code: str = Field(..., alias='currencyCode')
    value: str


class PriceDetail(BaseModel):
    base: PriceInfo
    final: List[PriceInfo]


class Price(BaseModel):
    retail: PriceDetail
    business: Optional[PriceDetail] = None


class SellerInfo(BaseModel):
    name: str
    rating: int
    ratings_count: int = Field(..., alias='ratingsCount')
    tier: str


class InventoryInfo(BaseModel):
    range: str


class Offer(BaseModel):
    id: str
    price: Price
    seller: SellerInfo
    inventory: InventoryInfo

    def get_price_value(self) -> float:
        if not self.price or not self.price.retail or not self.price.retail.final:
            return float('inf')

        for price_info in self.price.retail.final:
            if price_info and price_info.currency_code == "EUR":
                try:
                    return float(price_info.value)
                except (ValueError, TypeError):
                    return float('inf')

        return float('inf')

    def get_seller_name(self) -> str:
        return self.seller.name if self.seller and self.seller.name else "Unknown Seller"


class MetaInfo(BaseModel):
    page: int
    items_per_page: int = Field(..., alias='itemsPerPage')
    total_results: int = Field(..., alias='totalResults')


class OffersResponse(BaseModel):
    data: Optional[List[Offer]]
    meta: Optional[MetaInfo]

    def get_offers(self) -> List[Offer]:
        return self.data if self.data is not None else []

    def get_lowest_price_offer(self) -> Optional[Offer]:
        offers = self.get_offers()
        if not offers:
            return None

        return min(offers, key=lambda offer: offer.get_price_value())


class PricingSimulationResponse(BaseModel):
    income: Dict[str, str]
    final_price: Dict[str, str] = Field(..., alias="finalePrice")
