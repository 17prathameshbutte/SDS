# Testing Notes

The project uses Python's built-in `unittest` framework and Flask's test client.

## What is tested

- page loading
- registration and duplicate email checks
- login success and failure
- complaint submission and validation
- unauthorized access rules
- vote creation, change, and removal
- archive timing after resolution
- admin status updates
- Gemini failure handling

## Example command

```powershell
cd C:\Users\Pravin\Desktop\SDS
.\.venv\Scripts\python -m unittest discover -s tests -v
```
