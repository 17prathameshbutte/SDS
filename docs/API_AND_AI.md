# API and AI Notes

The project uses Gemini to suggest a maintenance category and priority when a valid API key exists. This addition is purposely small and safe.

## AI design

- The AI call is made from `services/gemini_service.py`.
- The integration uses the `gemini-3.5-flash-lite` model.
- The app validates the returned JSON before saving the suggestion.
- If the API key is missing or the API fails, the complaint still saves successfully.
- Passwords and other sensitive information are never sent to Gemini.
- Suggested categories are Electrical, Plumbing, Furniture, Civil, Cleaning, or Other.
- Suggested priority levels are Critical, Important, Normal, or Low.
- AI priority is only guidance; an administrator must review the actual situation.
