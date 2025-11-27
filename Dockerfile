FROM python:3.12-slim

WORKDIR /action

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code and entrypoint
COPY src/ ./src/
COPY action.py .

# Set the entrypoint
ENTRYPOINT ["python", "/action/action.py"]
