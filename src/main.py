import numpy as np
import numpy.typing as npt


def initialize_eval_matrix(n:int)->npt.NDArray:
    """
    評価行列を初期化する
    
    Parameters
    ----------
    n : int
        コミュニティの構成人数
    """
    e=np.zeros((n+1,n+1))
    for i in range(n+1):
        e[0][i]=1/n
        e[i][0]=1

    for i in range(n+1):
        e[i][i]=0

    print(e)
    print("評価行列が初期化されました")
    return e

def contribution_vector(e:npt.NDArray):
    """
    評価行列から貢献度ベクトルを計算する
    
    sum_{j=1}^N  E_ij = 1 for all i  を満たしているとき、
    つまり人iによる他のメンバーへの評価の総和が1であるとき、
    ペロン・フロベニウスの定理より固有値が1の固有ベクトルが存在する(らしい)

    
    Parameters
    ----------
    e : numpy.typing.NDArray
        評価行列
    """
    eigenvalues, eigenvectors = np.linalg.eig(e)
    print(eigenvalues)
    for l in eigenvalues:
        print(abs(l))
    print(eigenvectors)
    print(np.argmax(eigenvalues))
    print(eigenvectors[np.argmax(eigenvalues)])
    return eigenvectors[np.argmax(eigenvalues)]

def main():
    n=int(input("人数を入力してください"))
    gamma=float(input("自然回収率を設定してください"))

    eval=initialize_eval_matrix(n)
    contribution_vector(eval)



if __name__ == "__main__":
    main()
