# sagemaker-mlops-pipeline

An MLOps setup on AWS SageMaker: Terraform provisions the foundation (artifact
bucket, ECR repo, execution role, and a model registry), and a parameterised
SageMaker Pipeline handles preprocess, train, evaluate, and gated model
registration.

I built this to show the parts that turn a notebook model into something
shippable: versioned models, an approval gate, and a repeatable pipeline that
runs the same way in every environment.

## Pipeline

```
 PreprocessData ─► TrainModel ─► EvaluateModel ─► RegisterIfGoodEnough
   (SKLearn)        (XGBoost)     (AUC report)      │ AUC >= threshold?
                                                    ├─ yes ─► register (PendingManualApproval)
                                                    └─ no  ─► stop
```

A model is registered in the Model Package Group only if it beats the AUC
threshold, and it lands as `PendingManualApproval` so a human signs off before
deployment.

## Layout

| Path | Purpose |
|------|---------|
| [`terraform/`](terraform) | Artifact bucket, ECR repo, SageMaker execution role, model registry |
| [`pipelines/pipeline.py`](pipelines/pipeline.py) | The SageMaker Pipeline definition (4 steps, parameterised) |
| [`pipelines/requirements.txt`](pipelines/requirements.txt) | Python dependencies for building the pipeline |

## Usage

1. Provision infrastructure:

   ```bash
   cd terraform
   terraform init
   terraform apply -var="project=churn-model" -var="environment=dev"
   ```

2. Build and start the pipeline (from CI or locally), passing the Terraform
   outputs:

   ```python
   from pipelines.pipeline import get_pipeline

   pipeline = get_pipeline(
       region="eu-central-1",
       role="<execution_role_arn>",
       default_bucket="<artifact_bucket>",
       model_package_group_name="<model_package_group>",
   )
   pipeline.upsert(role_arn="<execution_role_arn>")
   pipeline.start(parameters={"InputDataUrl": "s3://.../raw/churn.csv"})
   ```

## Design choices

- **Registry + approval gate.** Models are versioned and require manual
  approval, so nothing reaches production unreviewed.
- **Quality gate in the pipeline.** Registration is conditional on an AUC
  threshold, not automatic.
- **Same definition everywhere.** Environment differences are parameters, not
  forks of the code.
- **Least-privilege bucket access** on the execution role, scoped to the
  project's artifact bucket.
- **Immutable, scanned images.** The ECR repo blocks tag overwrites and scans
  on push.

## Requirements

- Terraform >= 1.5, AWS provider >= 5.0
- Python 3.10+ with `sagemaker` (see `pipelines/requirements.txt`)

## Note

The pipeline references `processing/preprocess.py` and `processing/evaluate.py`
as job code. Those contain project-specific feature engineering and metric
computation; add them for your dataset.

## License

MIT. See [LICENSE](LICENSE).
