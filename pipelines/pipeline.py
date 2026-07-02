"""SageMaker training pipeline.

Defines a four-step pipeline that:

  1. Preprocesses raw data with a SKLearn processing job.
  2. Trains an XGBoost model.
  3. Evaluates the model and emits an evaluation report.
  4. Registers the model in the Model Package Group only when the evaluation
     metric clears a threshold, with manual approval required before deploy.

The pipeline is parameterised so the same definition runs in dev, staging, and
prod by changing inputs, not code. Wire it up from CI with `get_pipeline(...)`
followed by `pipeline.upsert(role_arn)` and `pipeline.start()`.
"""

from __future__ import annotations

import sagemaker
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.pipeline_context import PipelineSession
from sagemaker.workflow.parameters import (
    ParameterString,
    ParameterFloat,
)
from sagemaker.workflow.steps import ProcessingStep, TrainingStep
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.condition_step import ConditionStep
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.workflow.functions import JsonGet
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.processing import ProcessingInput, ProcessingOutput
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput


def get_pipeline(
    region: str,
    role: str,
    default_bucket: str,
    model_package_group_name: str,
    pipeline_name: str = "churn-training",
) -> Pipeline:
    """Build and return the SageMaker Pipeline object."""
    session = PipelineSession(default_bucket=default_bucket)

    # ---- Parameters (overridable at start time) -----------------------------
    input_data = ParameterString(name="InputDataUrl")
    instance_type = ParameterString(name="TrainingInstanceType", default_value="ml.m5.xlarge")
    model_approval_status = ParameterString(
        name="ModelApprovalStatus", default_value="PendingManualApproval"
    )
    auc_threshold = ParameterFloat(name="AucThreshold", default_value=0.80)

    # ---- Step 1: preprocessing ---------------------------------------------
    sklearn_processor = SKLearnProcessor(
        framework_version="1.2-1",
        role=role,
        instance_type="ml.m5.large",
        instance_count=1,
        base_job_name="churn-preprocess",
        sagemaker_session=session,
    )

    step_process = ProcessingStep(
        name="PreprocessData",
        processor=sklearn_processor,
        inputs=[ProcessingInput(source=input_data, destination="/opt/ml/processing/input")],
        outputs=[
            ProcessingOutput(output_name="train", source="/opt/ml/processing/train"),
            ProcessingOutput(output_name="validation", source="/opt/ml/processing/validation"),
            ProcessingOutput(output_name="test", source="/opt/ml/processing/test"),
        ],
        code="processing/preprocess.py",
    )

    # ---- Step 2: training (built-in XGBoost) --------------------------------
    image_uri = sagemaker.image_uris.retrieve("xgboost", region=region, version="1.7-1")
    xgb = Estimator(
        image_uri=image_uri,
        role=role,
        instance_type=instance_type,
        instance_count=1,
        output_path=f"s3://{default_bucket}/{pipeline_name}/models",
        sagemaker_session=session,
    )
    xgb.set_hyperparameters(
        objective="binary:logistic",
        num_round=200,
        max_depth=5,
        eta=0.2,
        subsample=0.8,
        eval_metric="auc",
    )

    step_train = TrainingStep(
        name="TrainModel",
        estimator=xgb,
        inputs={
            "train": TrainingInput(
                s3_data=step_process.properties.ProcessingOutputConfig.Outputs["train"].S3Output.S3Uri,
                content_type="text/csv",
            ),
            "validation": TrainingInput(
                s3_data=step_process.properties.ProcessingOutputConfig.Outputs["validation"].S3Output.S3Uri,
                content_type="text/csv",
            ),
        },
    )

    # ---- Step 3: evaluation -------------------------------------------------
    evaluation_report = PropertyFile(
        name="EvaluationReport", output_name="evaluation", path="evaluation.json"
    )

    step_eval = ProcessingStep(
        name="EvaluateModel",
        processor=sklearn_processor,
        inputs=[
            ProcessingInput(
                source=step_train.properties.ModelArtifacts.S3ModelArtifacts,
                destination="/opt/ml/processing/model",
            ),
            ProcessingInput(
                source=step_process.properties.ProcessingOutputConfig.Outputs["test"].S3Output.S3Uri,
                destination="/opt/ml/processing/test",
            ),
        ],
        outputs=[ProcessingOutput(output_name="evaluation", source="/opt/ml/processing/evaluation")],
        code="processing/evaluate.py",
        property_files=[evaluation_report],
    )

    # ---- Step 4: conditional register --------------------------------------
    step_register = RegisterModel(
        name="RegisterModel",
        estimator=xgb,
        model_data=step_train.properties.ModelArtifacts.S3ModelArtifacts,
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.t2.medium", "ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=model_package_group_name,
        approval_status=model_approval_status,
    )

    condition_gate = ConditionGreaterThanOrEqualTo(
        left=JsonGet(
            step_name=step_eval.name,
            property_file=evaluation_report,
            json_path="metrics.auc.value",
        ),
        right=auc_threshold,
    )

    step_condition = ConditionStep(
        name="RegisterIfGoodEnough",
        conditions=[condition_gate],
        if_steps=[step_register],
        else_steps=[],
    )

    return Pipeline(
        name=pipeline_name,
        parameters=[input_data, instance_type, model_approval_status, auc_threshold],
        steps=[step_process, step_train, step_eval, step_condition],
        sagemaker_session=session,
    )
