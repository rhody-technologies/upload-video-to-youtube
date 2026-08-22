FROM public.ecr.aws/lambda/python:3.12

# Copy the package requirements to the image
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install packages using pip
RUN pip install --no-cache-dir -r requirements.txt -t "${LAMBDA_TASK_ROOT}"

# Copy the main executable script to the image
COPY main.py ${LAMBDA_TASK_ROOT}/

# Copy the secrets to the image
COPY client_secret.json token_youtube.json token_sheets.json ${LAMBDA_TASK_ROOT}/

# Run command during container start
CMD ["main.handler"]
