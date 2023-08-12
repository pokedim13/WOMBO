import typing
import re
import io
import asyncio

import httpx
from PIL import Image

from wombo.urls import urls, headers_gen, check_headers, auth_key_headers
from wombo.models import CreateTask, CheckTask
from wombo.base_models import BaseDream


class AsyncDream(BaseDream):
    def __init__(self, out_msg: str = "") -> None:
        self.client = httpx.AsyncClient()
        self.out_msg: str = out_msg

    async def _get_js_filename(self) -> str:
        """
        Get name JS file, from extract Google Key
        """
        response = await self.client.get(urls["js_filename"])
        js_filename = re.findall(r"_app-(\w+)", response.text)

        return js_filename[0]

    async def _get_google_key(self) -> str:
        """
        Get Google Key from JS file
        """
        js_filename = await self._get_js_filename()

        url = f"https://dream.ai/_next/static/chunks/pages/_app-{js_filename}.js"
        response = await self.client.get(url)

        key = re.findall(r'"(AI\w+)"', response.text)
        return key[0]

    async def _get_auth_key(self) -> str:
        """
        Get Auth Key from JS file
        """
        params = {"key": await self._get_google_key()}
        json_data = {"returnSecureToken": True}

        response = await self.client.post(
            urls["auth_key"],
            headers=auth_key_headers,
            params=params,
            json=json_data,
            timeout=20,
        )

        result = response.json()
        return result["idToken"]

    # ============================================================================================= #
    async def create_task(self, text: str, style: Style) -> CreateTask:
        """
        We set the task to generate an image and use a certain TASK_ID, which we will track
        """
        draw_url = "https://paint.api.wombo.ai/api/v2/tasks"
        auth_key = await self._get_auth_key()
        data = (
                '{"is_premium":false,"input_spec":{"prompt":"%s","style":%d,"display_freq":10}}'
                % (text[:200], style.value)
        )

        response = await self.client.post(
            url=draw_url, headers=headers_gen(auth_key), data=data, timeout=20
        )
        result_row = response.json()
        result = CreateTask.parse_obj(result_row)
        return result

    async def check_task(self, task_id: str, only_bool: bool = False) -> Union[CheckTask, bool]:
        """
        Checks if the image has already been generated by task_id
        """
        img_check_url = f"https://paint.api.wombo.ai/api/v2/tasks/{task_id}"

        response = await self.client.get(img_check_url, headers=check_headers, timeout=10)
        result = CheckTask.parse_obj(response.json())
        return bool(result.photo_url_list) if only_bool else result

    async def generate_image(
            self,
            text: str,
            style: Style = Style.buliojourney_v2,
            timeout: int = 60,
            check_for: int = 3
    ) -> CheckTask:
        """
        Generate image
        """
        task = await self.create_task(text=text, style=style)

        while timeout > 0:
            sleep(check_for)
            timeout -= check_for
            check_task = await self.check_task(task.id)

            if check_task.photo_url_list and check_task.state != "generating":
                return check_task
        else:
            TimeoutError(self.out_msg)

    # ============================================================================================= #

    async def gif(self, url_list: typing.List, thread: bool = True) -> io.BytesIO:
        """
        Creating a streaming object with gif
        """
        tasks = [self.client.get(url) for url in url_list]
        res = await asyncio.gather(*tasks)
        frames = [Image.open(io.BytesIO(url.content)) for url in res]
        return (
            await asyncio.to_thread(self.save_frames_as_gif, (frames))
            if thread
            else self.save_frames_as_gif(frames)
        )


async def main():
    dream = AsyncDream()
    task = await dream.generate("Anime waifu in bikini")
    with open("file.gif", 'wb') as f:
        gif = await dream.gif(task.photo_url_list)
        f.write(gif.getvalue())


if __name__ == "__main__":
    asyncio.run(main())
