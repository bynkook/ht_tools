import json
import glob


def extract_payload(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the JSON part after "data: "
    if content.startswith("data: "):
        json_str = content[6:].strip()
        try:
            data = json.loads(json_str)

            # Extract the actual payload
            if "result" in data:
                if "structuredContent" in data["result"]:
                    payload = data["result"]["structuredContent"]
                elif "content" in data["result"]:
                    # Try to find JSON in content
                    for item in data["result"]["content"]:
                        if item.get("type") == "text":
                            try:
                                payload = json.loads(item["text"])
                                break
                            except json.JSONDecodeError:
                                pass
                    else:
                        payload = data["result"]
                else:
                    payload = data["result"]
            else:
                payload = data

            # Write back the formatted payload
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"Extracted payload for {file_path}")
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON in {file_path}: {e}")
    else:
        print(f"File {file_path} does not start with 'data: '")


for file_path in glob.glob(".sisyphus/evidence/task-2-lx-*-raw-*.json"):
    extract_payload(file_path)
