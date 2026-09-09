from pydantic import BaseModel, ConfigDict # BaseModel is used to define the structure of the data that will be sent to the API, ConfigDict is used to configure the model

class ItemCreate(BaseModel):
    # This line of code configures the model to allow attributes to be used as keyword arguments.
    model_config = ConfigDict(from_attributes=True)
    
    title: str
    description: str
    price: float
    stock: int
    image_url: str = ""

class ItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    price: float | None = None
    stock: int | None = None
    image_url: str | None = None
class ItemResponse(ItemCreate):
    id: int

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class CheckoutLine(BaseModel):
    item_id: int
    quantity: int

class CheckoutRequest(BaseModel):
    lines: list[CheckoutLine]
    ship_to: str
