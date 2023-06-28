# https://docs.gpytorch.ai/en/stable/examples/01_Exact_GPs/Simple_GP_Regression.html

import torch
import gpytorch
import matplotlib
import yaml
from os import listdir, remove, mkdir
from os.path import exists

from preprocessing import prepare_data
from visualisation import plot_results


with open("config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)


# We will use the simplest form of GP model, exact inference
class ExactGPModel(gpytorch.models.ExactGP):
    def __init__(self, train_x, train_y, likelihood, kernel, training_iter=50):
        super(ExactGPModel, self).__init__(train_x, train_y, likelihood)
        self.mean_module = gpytorch.means.ConstantMean()
        self.covar_module = kernel
        self.likelihood = likelihood
        self.training_iter = training_iter
        self.train_x = train_x
        self.train_y = train_y
        # self.test_x = test_x 

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        return gpytorch.distributions.MultivariateNormal(mean_x, covar_x)

    def train_loop(self) -> float:
        # Set the modules to train mode
        self.train()
        self.likelihood.train()

        # Use the adam optimizer
        optimizer = torch.optim.Adam(self.parameters(), lr=1e-2)  # Includes GaussianLikelihood parameters

        # "Loss" for GPs - the marginal log likelihood
        mll = gpytorch.mlls.ExactMarginalLogLikelihood(self.likelihood, self)

        for i in range(self.training_iter):
            # Zero gradients from previous iteration
            optimizer.zero_grad()
            # Output from model
            output = self(self.train_x)
            # Calc loss and backprop gradients
            loss = - mll(output, self.train_y)
            loss.backward()
            print('Iter %d/%d - Loss: %.3f  lengthscale: %.3f,  alpha: %.3f,  noise: %.3f  output scale: %.3f' % (
                i + 1, self.training_iter, loss.item(),
                self.covar_module.base_kernel.lengthscale.item(),
                self.covar_module.base_kernel.alpha.item(),
                self.likelihood.noise.item(),
                self.covar_module.outputscale.item()
            ))
            optimizer.step()

        return loss.item()
    
def save_best_models(model, loss, n_models = 3):
    """ Looks at the saved models. If the current model is better than one of them, it is saved instead. """
    SAVE_PATH = CONFIG["gpytorch_save_path"]
    if not exists(SAVE_PATH):
        mkdir(SAVE_PATH)
    saved_models = listdir(SAVE_PATH)

    if len(saved_models) < n_models:
        torch.save(model.state_dict(), f"{SAVE_PATH}/{loss:.4f}.pth")
    else:
        for saved_model in saved_models:
            if loss < float(saved_model[:-4]):
                torch.save(model.state_dict(), f"{SAVE_PATH}/{loss:.4f}.pth")
                remove(f"{SAVE_PATH}/{saved_model}")
                break


if __name__ == "__main__":
    matplotlib.use("TKAgg")
    # # Gpytorch example data
    # train_x = torch.linspace(0, 1, 100)
    # train_y = torch.sin(train_x * (2 * math.pi)) + torch.randn(train_x.size()) * math.sqrt(0.04)
    # test_x = torch.linspace(0, 1, 50)

    # Get data
    X_train, y_train, X_test, y_test, X_val, y_val, X_grid = prepare_data()
    train_x = torch.tensor(X_train, dtype=torch.float32)
    train_y = torch.tensor(y_train, dtype=torch.float32)
    test_x = torch.tensor(X_grid, dtype=torch.float32)

    # Init model
    kernel = gpytorch.kernels.ScaleKernel(gpytorch.kernels.RQKernel(lengthscale=1, lengthscale_constraint=gpytorch.constraints.Interval(0.5, 1), alpha=1, alpha_constraint=gpytorch.constraints.Interval(5, 100)))
    likelihood = gpytorch.likelihoods.GaussianLikelihood()
    model = ExactGPModel(train_x, train_y, likelihood, kernel, 100)

    # Train model
    loss = model.train_loop()

    # Get into evaluation (predictive posterior) mode
    model.eval()
    likelihood.eval()

    # Make predictions by feeding model through likelihood
    with torch.no_grad(), gpytorch.settings.fast_pred_var():
        observed_pred = likelihood(model(test_x))
        means = observed_pred.mean.numpy()
        variances = observed_pred.variance.numpy()

    # Save and load the model with the loss as its name
    save_best_models(model, loss)

    plot_results(test_x, means, variances, train_x, train_y)

