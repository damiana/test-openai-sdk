from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-6-luna",
    input="Escreva uma frase de um poema do Casimiro de Abreu.",
)

print(response.output_text)