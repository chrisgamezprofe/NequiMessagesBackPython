#!/usr/bin/env python3
"""Punto de entrada de la app CDK. propuesta ilustrativa, no un
despliegue verificado contra una cuenta AWS real."""
import aws_cdk as cdk

from infrastructure_stack import ChatApiInfrastructureStack

app = cdk.App()
ChatApiInfrastructureStack(
    app,
    "ChatApiInfrastructureStack",
    env=cdk.Environment(region="us-east-1"),
)

app.synth()
