from agent import expense_agent
from IPython.display import Image

png_data = expense_agent.get_graph().draw_mermaid_png()
with open("graph_image.png", "wb") as f:
    f.write(png_data)

