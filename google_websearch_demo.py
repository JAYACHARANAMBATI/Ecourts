import requests

# Your credentials
API_KEY = "AIzaSyD6bheRnG1XqDK3ybX-Mbd3xjx94sbgXfo"
CSE_ID = "05f08500073ad4243"

def google_search(query, api_key=API_KEY, cse_id=CSE_ID, num_results=5):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": num_results
    }

    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("items", []):
        results.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet")
        })
    
    return results

# Example usage
if __name__ == "__main__":
    query = input("Enter your search query: ")
    search_results = google_search(query)

    for idx, result in enumerate(search_results, start=1):
        print(f"\nResult {idx}")
        print(f"Title: {result['title']}")
        print(f"Link: {result['link']}")
        print(f"Snippet: {result['snippet']}")
