"""Ошибки программного интерфейса.

Интерфейс диспетчера (SPA «Чистый Липецк») читает текст ошибки из поля
`message` — так записано в его контракте. FastAPI по умолчанию кладёт текст
в `detail`, и внешний интерфейс показал бы «Unauthorized» вместо понятной
фразы.

Обработчик заводится **только** для этого класса ошибок. Перехватывать все
HTTPException нельзя: страницы интерфейса сообщают о необходимости входа
через `HTTPException(303)` с заголовком `Location`, и общий обработчик
превратил бы переадресацию в JSON — вход в систему перестал бы работать.
"""

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """Ошибка программного интерфейса с текстом для человека."""

    def __init__(self, status_code: int, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.message = message


async def api_error_handler(request, error: ApiError) -> JSONResponse:
    """Отдаёт ошибку в формате контракта: `message` плюс привычный `detail`."""

    return JSONResponse(
        {"message": error.message, "detail": error.message},
        status_code=error.status_code,
    )
