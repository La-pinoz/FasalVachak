import asyncio, os
from dotenv import load_dotenv
load_dotenv('.env')
from tts.rime_tts import create_tts_client
async def main():
    tts, session = create_tts_client()
    try:
        async with tts.synthesize('Namaste') as stream:
            async for s in stream:
                print('got frame', s.frame.samples_per_channel)
    except Exception as e:
        print('Error:', type(e), e)
    finally:
        await session.close()
asyncio.run(main())
