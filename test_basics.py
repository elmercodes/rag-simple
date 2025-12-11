from openai import OpenAI, APIStatusError, APIConnectionError
import os

client = OpenAI()

base = "hello " * 200  # ~1200 characters
messages = [{"role": "user", "content": base}]

while True:
    total = sum(len(m["content"]) for m in messages)
    print(f"\nTrying with {len(messages)} messages, total {total} chars")

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
        )
        print("  -> SUCCESS:", resp.choices[0].message.content[:50])
        messages.append({"role": "user", "content": base})

    except APIStatusError as e:
        print("  -> APIStatusError", e.status_code, e.message)
        break

    except APIConnectionError as e:
        print("  -> APIConnectionError", e)
        break

    except Exception as e:
        print("  -> OTHER ERROR:", type(e), e)
        break
