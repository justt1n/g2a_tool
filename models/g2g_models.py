from typing import List, Optional, Dict, Any

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
        if not self.price or not self.price.retail or not self.price.retail.base:
            return float('inf')
        try:
            if self.price.retail.base.currency_code == "EUR":
                return float(self.price.retail.base.value)
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


class OfferProductInfo(BaseModel):
    id: str
    name: str


class OfferDetails(BaseModel):
    id: str
    type: str
    status: str
    price: str
    currency: str = "EUR"  # Mặc định hoặc lấy từ đâu đó nếu API trả về

    # Bổ sung các trường thiếu
    businessPrice: Optional[str] = None
    visibility: Optional[str] = None
    inventory: Optional[Dict[str, Any]] = None

    # finalPrice là Dict map country code -> price string (VD: {"pl": "12.44"})
    finalPrice: Optional[Dict[str, str]] = None
    businessFinalPrice: Optional[Dict[str, str]] = None

    product: Optional[OfferProductInfo] = None

    def get_base_price(self) -> float:
        """Helper để lấy giá gốc (Base Price) dạng float"""
        try:
            return float(self.price)
        except (ValueError, TypeError):
            return 0.0


class OfferDetailsResponse(BaseModel):
    data: OfferDetails


class UpdatePricePayload(BaseModel):
    retail: str


class UpdateInventoryPayload(BaseModel):
    size: int


class UpdateOfferVariantPayload(BaseModel):
    visibility: str = "all"
    active: bool = True
    archive: bool = False
    price: UpdatePricePayload
    inventory: Optional[UpdateInventoryPayload] = None


class UpdateOfferPayload(BaseModel):
    offerType: str
    variant: UpdateOfferVariantPayload
