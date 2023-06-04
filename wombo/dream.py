import typing
import time
import re
import io

import httpx
from PIL import Image

from wombo.urls import urls, headers_gen, check_headers, auth_key_headers
from wombo.models import CreateTask, CheckTask
from wombo.base_dream import BaseDream


class Dream(BaseDream):
    def __init__(self) -> None:
        self.client = httpx.Client()

    def _get_js_filename(self) -> str:
        """Получает имя JS файла, откуда извлекаем Google Key"""

        response = self.client.get(urls["js_filename"])
        js_filename = re.findall(r"_app-(\w+)", response.text)

        return js_filename[0]

    def _get_google_key(self) -> str:
        """Получаем Google Key из JS файла"""
        js_filename = self._get_js_filename()

        url = f"https://dream.ai/_next/static/chunks/pages/_app-{js_filename}.js"
        response = self.client.get(url)

        key = re.findall(r'"(AI\w+)"', response.text)
        return key[0]

    def _get_auth_key(self) -> str:
        params = {"key": self._get_google_key()}
        json_data = {"returnSecureToken": True}

        response = self.client.post(
            urls["auth_key"],
            headers=auth_key_headers,
            params=params,
            json=json_data,
            timeout=20,
        )

        result = response.json()
        return result["idToken"]

    # ============================================================================================= #
    def create_task(self, text: str, style: int = 84) -> CreateTask:
        """We set the task to generate an image and use a certain TASK_ID, which we will track"""
        draw_url = "https://paint.api.wombo.ai/api/v2/tasks"
        auth_key = self._get_auth_key()
        data = (
            '{"is_premium":false,"input_spec":{"prompt":"%s","style":%d,"display_freq":10}}'
            % (text[:200], style)
        )

        response = self.client.post(
            draw_url, headers=headers_gen(auth_key), data=data.encode(), timeout=20
        )
        result = response.json()
        result = CreateTask.parse_obj(result)
        return result

    def check_task(self, task_id: str, only_bool: bool = True) -> CheckTask | bool:
        """Checks if the image has already been generated by task_id"""
        img_check_url = f"https://paint.api.wombo.ai/api/v2/tasks/{task_id}"

        response = self.client.get(img_check_url, headers=check_headers, timeout=10)
        result = CheckTask.parse_obj(response.json())
        return bool(result.photo_url_list) if only_bool else result

    def generate(self, text: str, style: int = 84, gif: bool = False):
        """Generate image"""
        task = self.create_task(text=text, style=style)
        time.sleep(2)
        for _ in range(100):
            task = self.check_task(task_id=task.id, only_bool=False)
            if task.photo_url_list and task.state != "generating":
                res = self.gif(task.photo_url_list) if gif else task
                break
            time.sleep(2)
        return res

    async def gif(self, url_list: typing.List) -> io.BytesIO:
        """Creating a streaming object with gif"""
        urls = [self.client.get(url) for url in url_list]
        frames = [Image.open(io.BytesIO(url.content)) for url in urls]
        return self.save_frames_as_gif(frames)


if __name__ == "__main__":
    dream = Dream()
    print(dream.check_task("22faeb1b-6adb-4210-9ac8-9289752d0a4a"))
