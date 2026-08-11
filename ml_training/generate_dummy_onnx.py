import argparse
from pathlib import Path
import onnx
from onnx import helper, TensorProto

def main():
    parser = argparse.ArgumentParser(description="Generar modelo ONNX dummy para pruebas de regresión de color")
    parser.add_argument("--output", type=str, default="../backend/.runtime/models/color_regression.onnx", help="Ruta de salida")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Definir entrada y salida
    # Entrada: batch_size x 3 (RGB) x 224 x 224
    # Salida: batch_size x 3 (valores de color predichos)
    input_tensor = helper.make_tensor_value_info('input', TensorProto.FLOAT, [None, 3, 224, 224])
    output_tensor = helper.make_tensor_value_info('output', TensorProto.FLOAT, [None, 3])

    # Nodo 1: GlobalAveragePool para reducir 224x224 a 1x1 por canal
    pool_node = helper.make_node(
        'GlobalAveragePool',
        inputs=['input'],
        outputs=['pooled']
    )

    # Nodo 2: Flatten para convertir de (batch, 3, 1, 1) a (batch, 3)
    flatten_node = helper.make_node(
        'Flatten',
        inputs=['pooled'],
        outputs=['output'],
        axis=1
    )

    # Crear el grafo de ONNX
    graph_def = helper.make_graph(
        [pool_node, flatten_node],
        'color-regression-dummy',
        [input_tensor],
        [output_tensor]
    )

    # Crear y guardar el modelo con opset version compatible
    model_def = helper.make_model(
        graph_def,
        producer_name='dummy-regressor-generator',
        opset_imports=[helper.make_opsetid("", 15)]
    )
    onnx.checker.check_model(model_def)
    onnx.save(model_def, str(output_path))
    print(f"Modelo ONNX dummy generado exitosamente en: {output_path}")

if __name__ == "__main__":
    main()
