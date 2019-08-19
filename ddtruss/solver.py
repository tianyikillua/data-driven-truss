import numpy as np
from scipy.spatial import cKDTree


class DataDrivenSolver:
    """
    Data-driven solver for truss structures

    Args
    ----
    truss :
        Object defining the truss structure
    """

    def __init__(self, truss):
        self.truss = truss

    def load_material_data(self, material_data):
        """
        Load one-dimensional material data

        Args
        ----
        material_data : ndarray, shape (n_data, 2)
            Experimentally measured ``(strain, stress)`` pairs
        """
        assert material_data.shape[1] == 2
        self.material_data = material_data
        self.n_data = material_data.shape[0]
        self.data_tree = None

    def solve(self, A=1, U_dict={}, F_dict={}, n_iterations=100, E_num=None):
        """
        Solve the static equilibrium problem for the truss structure using a
        data-driven approach

        Args
        ----
        A : float or ndarray, shape (n_lines, )
            Cross section area
        U_dict : dict
            Prescribed displacement ``{point_id: (Ux, Uy), ...}``
        F_dict : dict
            Prescribed nodal force ``{point_id: (Fx, Fy), ...}``
        n_iterations : int
            Maximimum iteration for the data-driven solver
        E_num : float, optional
            Numerical value

        Returns
        -------
        u : ndarray, shape (n_ddl, )
            Displacement solution
        eps : ndarray, shape (n_lines, )
            Strain
        sig : ndarray, shape (n_lines, )
            Stress
        f_obj_iter : ndarray
            Objective function value at each iteration
        """
        # Initialize the truss solver
        if E_num is None:
            ind = np.isclose(self.material_data[:, 0], 0)
            E_secent = self.material_data[~ind, 1] / self.material_data[~ind, 0]
            E_num = E_secent.mean()
        self.sqE = np.sqrt(E_num)

        # Initialize local states
        idx = np.random.randint(self.n_data, size=self.truss.n_lines)
        eps_sig_ = self.material_data[idx]

        # Define the zeroed Dirichlet conditions
        U_dict_0 = {}
        for key in U_dict:
            U_dict_0[key] = [0 if value is not None else None for value in U_dict[key]]

        f_obj_iter = []
        while len(f_obj_iter) <= n_iterations:
            # Solve the 1st problem for u driven by initial stress
            sig0 = -E_num * eps_sig_[:, 0]
            if len(f_obj_iter) == 0:
                construct_K = True
            else:
                construct_K = False
            u, eps, _ = self.truss.solve(
                A=A, E=E_num, U_dict=U_dict, sig0=sig0, construct_K=construct_K
            )

            # Solve the 2nd problem for eta driven by initial stress and applied force
            sig0 = eps_sig_[:, 1]
            _, eps_eta, _ = self.truss.solve(
                A=A, E=E_num, U_dict=U_dict_0, F_dict=F_dict, sig0=sig0
            )
            sig = eps_sig_[:, 1] + E_num * eps_eta

            eps_sig = np.hstack([eps.reshape((-1, 1)), sig.reshape((-1, 1))])
            eps_sig_idx, eps_sig_, f_obj = self._optimal_local_states(eps_sig)
            f_obj_iter.append(f_obj)

            # Check for convergence
            if np.allclose(idx, eps_sig_idx):
                return u, eps_sig[:, 0], eps_sig[:, 1], np.array(f_obj_iter)
            else:
                idx = eps_sig_idx.copy()
        else:
            return RuntimeError(
                f"Data-driven solver not converged after {n_iterations} iterations"
            )

    def _optimal_local_states(self, eps_sig):
        if self.data_tree is None:
            eps_sig_data = self.material_data.copy()
            eps_sig_data[:, 0] *= self.sqE
            eps_sig_data[:, 1] /= self.sqE
            self.data_tree = cKDTree(eps_sig_data)

        eps_sig_rescaled = eps_sig.copy()
        eps_sig_rescaled[:, 0] *= self.sqE
        eps_sig_rescaled[:, 1] /= self.sqE
        dist, idx = self.data_tree.query(eps_sig_rescaled)
        f_obj = self.truss.integrate(dist)
        eps_sig_optimal = self.material_data[idx]
        return idx, eps_sig_optimal, f_obj
